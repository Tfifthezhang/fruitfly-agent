"""Independent research actions reuse Run services and optional source adapters."""
import asyncio
from dataclasses import asdict
import json
import yaml
from pathlib import Path
from uuid import uuid4

from fruitfly_agent.improvement.contracts.tasks import Resource
from fruitfly_agent.run.storage.artifacts import DataArtifactStore
from fruitfly_agent.run.storage.research_bundles import ArtifactPort
from fruitfly_agent.run.improvement.service import ResearchService
from fruitfly_agent.improvement.contracts.versions import canonical_json


def resolve_inputs(outputs, args):
    """Resolve each declared slot independently, retaining producer provenance."""
    requested = getattr(args, 'named_inputs', None)
    if requested is None:
        # Explicit bundle collections are classified by their manifests, never
        # by argument position. Raw hashes need an explicit named grant.
        from fruitfly_agent.improvement.contracts.bundles import ResearchBundle
        requested = {'batches': [], 'evidence': [], 'assessments': [], 'context': []}
        for value in args.inputs:
            if value.startswith('sha256:'):
                raise ValueError('use a typed bundle or named research input instead of an untyped hash')
            path = Path(value).expanduser()
            if not path.is_absolute():
                path = outputs.workspace / path
            if path.is_dir():
                path = path / 'bundle.json'
            bundle = ResearchBundle.from_dict(json.loads(path.read_text()))
            if bundle.kind == 'propose' and args.command == 'execute':
                if requested.get('harness'):
                    raise ValueError('execute requires one explicitly selected harness')
                requested['harness'] = str(path)
                args.harness_bundle = str(path)
            elif bundle.kind in {'import', 'eval', 'execute', 'assess'}:
                requested['batches'].append(str(path))
            else:
                requested[{'organize': 'evidence', 'compare': 'assessments'}.get(bundle.kind, 'context')].append(str(path))
    from dataclasses import replace
    from fruitfly_agent.improvement.contracts.stages import StageInputs
    slots, producers = {}, []
    for name in ('harness', 'batches', 'evidence', 'assessments', 'context'):
        values = requested.get(name, [])
        if name == 'harness':
            # Proposal harness selection is resolved as a complete config by the
            # configuration loader; its snapshot is bound after target assembly.
            values = [] if args.command == 'propose' or isinstance(values, str) and values.endswith(('.yaml', '.yml')) else ([values] if values else [])
        resources = []
        for index, value in enumerate(values):
            entries, origins = outputs.inputs((value,), args.command)
            producers.extend(origins)
            resources.extend(replace(entry, path=name + '/' + str(index) + '/' + entry.path) for entry in entries)
        slots[name] = resources[0] if name == 'harness' and resources else None if name == 'harness' else tuple(resources)
    named = StageInputs(**slots)
    if args.command == 'propose' and getattr(args, 'harness_bundle', None):
        entries, origins = outputs.inputs((args.harness_bundle,), args.command)
        producers.extend(origins)
        named = replace(named, context=(*named.context, *(replace(entry,
            path='parent/' + entry.path) for entry in entries)))
    resources = (() if named.harness is None else (named.harness,)) + named.batches + named.evidence + named.assessments + named.context
    return resources, producers, named


async def _dispatch(args, workspace, outputs, reporting):
    artifacts = ArtifactPort(outputs.artifacts)
    service = ResearchService(workspace, args.study, artifacts, journal=outputs.journal())
    reporting['service'] = service
    if args.command in {'inspect', 'resume'}:
        state = service.controller.state()
        return {'study': args.study, 'revisions': state.revisions, 'attempts': state.attempts,
            'unresolved': state.unresolved, 'notes': state.notes,
            'action': 'Inspect then select a stage; unresolved work is never automatically replayed.'}
    if args.command == 'fork':
        service.store.fork(args.target)
        return {'study': args.study, 'fork': args.target}
    if args.command == 'import':
        configuration = {'action': 'import', 'source': str(Path(args.path).resolve()), 'related_records': getattr(args, 'related_records', None),
            'task_names': getattr(args, 'task_names', ()), 'evidence_paths': getattr(args, 'evidence_paths', {}),
            'historical_configuration': {'status': 'Retained in source artifacts where available; not reconstructed from current settings.'}}
        if getattr(args, 'config', None):
            configuration['authored'] = yaml.safe_load(Path(args.config).read_text())
        reporting.update(configuration=configuration)
        _capture_configuration(outputs, reporting)
        if args.source == 'eval':
            from fruitfly_eval.improvement.history import import_history
            batch = import_history(Path(args.path).resolve(), artifacts, related_records=getattr(args, 'related_records', None),
                task_names=getattr(args, 'task_names', ()), evidence_paths=getattr(args, 'evidence_paths', None))
        else:
            from fruitfly_agent.improvement.contracts.research import ResearchBatch
            batch = ResearchBatch.from_dict(json.loads(Path(args.path).read_text()))
        if not service.controller.state().revisions:
            service.revise({'source': args.source}, direction='Continue research from retained records.')
        resource = service.put('batch.json', batch.to_dict())
        reporting.update(inputs=(resource,))
        _capture_configuration(outputs, reporting)
        return await service.perform('import', (resource,), fresh=args.fresh, retry_unresolved=args.retry_unresolved)
    if args.command == 'eval':
        from ..configuration import load_configuration
        from ..composition import prepare_experiment
        from ..records import RunRecords
        from .evaluate import run as evaluate
        config = load_configuration(workspace, args.config, stage='eval')
        prepared = prepare_experiment(config, 'eval')
        reporting.update(configuration={**prepared.summary(), 'authored': yaml.safe_load(config.path.read_text())})
        _capture_configuration(outputs, reporting)
        service.revise(reporting['configuration'], direction='Execute one fixed configuration.')
        async def execute_eval(spec):
            from fruitfly_agent.improvement.contracts.activities import ActivityResult
            from fruitfly_eval.improvement.history import import_history
            records = RunRecords(workspace)
            record = records.create('eval', prepared.summary())
            import threading
            cancelled = threading.Event()
            def progress(event):
                if cancelled.is_set():
                    raise KeyboardInterrupt('research Eval cancelled')
            with records.owner(record):
                task = asyncio.create_task(asyncio.to_thread(evaluate, prepared, record, records, progress))
                try:
                    result = await asyncio.shield(task)
                except (asyncio.CancelledError, KeyboardInterrupt):
                    cancelled.set()
                    if record['links'].get('eval'):
                        from fruitfly_eval.api import stop_evaluation
                        from fruitfly_agent.run.improvement.configuration import ResearchDocument
                        stop_evaluation(record['links']['eval'], output_root=ResearchDocument(config.path).root / 'eval')
                    try:
                        await asyncio.wait_for(asyncio.shield(task), 10)
                    except TimeoutError as exc:
                        from fruitfly_agent.improvement.contracts.activities import UnresolvedActivity
                        raise UnresolvedActivity('Eval cleanup could not be confirmed; inspect its retained intent before retrying') from exc
                    except (KeyboardInterrupt, asyncio.CancelledError):
                        if not task.done():
                            from fruitfly_agent.improvement.contracts.activities import UnresolvedActivity
                            raise UnresolvedActivity('Eval cancellation remains unresolved')
                    raise
            batch = import_history(Path(result['report']).parent, artifacts)
            return ActivityResult((service.put('batch.json', batch.to_dict()),))
        service = ResearchService(workspace, args.study, artifacts, journal=outputs.journal(),
            external_stages={'eval': execute_eval})
        reporting['service'] = service
        return await service.perform('eval', (), fresh=args.fresh, retry_unresolved=args.retry_unresolved)
    if args.command == 'execute':
        from ..configuration import load_configuration
        from ..composition import prepare_experiment, application_factory
        from fruitfly_agent.interactive import AgentApplication
        config = load_configuration(workspace, args.config)
        requested = config.snapshot()
        inputs, producers, named = resolve_inputs(outputs, args)
        if not args.apply_to_current and 'research' not in yaml.safe_load(config.path.read_text()):
            # A saved candidate is an executable complete configuration, not a
            # patch whose old baseline must equal the current daily profile.
            first = Path(args.harness_bundle)
            if not args.harness_bundle.startswith('sha256:'):
                if first.is_dir(): first = first / 'bundle.json'
                frozen = sorted(first.parent.glob('*/candidate/config.yaml'))
                if len(frozen) == 1:
                    from dataclasses import replace
                    config = replace(config, runtime={**config.runtime, 'config': str(frozen[0])})
        prepared = prepare_experiment(config, 'improvement')
        runtime_directory = outputs.root / 'research-runtime'
        runtime_directory.mkdir(parents=True, exist_ok=True)
        stage = runtime_directory / uuid4().hex
        runtime = prepared.stage_runtime(stage)
        factory = application_factory(prepared, runtime)
        application = AgentApplication(factory)
        try:
            await application.start()
            executing = factory.research_service(args.study, prepared.request, artifacts=artifacts)
            reporting['service'] = executing
            executing.store = outputs.journal()
            executing.artifacts = artifacts
            executing.controller.journal = executing.store
            executing.controller.artifacts = artifacts
            if not executing.controller.state().revisions:
                executing.revise({'source': prepared.source.source_identity}, direction=config.improvement.direction)
            reporting.update(configuration={**prepared.summary(), 'requested': requested,
                'authored': yaml.safe_load(config.path.read_text()),
                'candidate_configuration_mode': 'apply-to-current' if args.apply_to_current else 'saved-snapshot'}, inputs=inputs, producers=producers)
            _capture_configuration(outputs, reporting)
            if 'research' in yaml.safe_load(config.path.read_text()):
                from dataclasses import replace
                effective_harness = executing.put('execution-harness.json', executing.harness.to_dict())
                named = replace(named, harness=effective_harness)
                reporting['inputs'] = (*inputs, effective_harness)
            return await executing.perform_named('execute', named, parameters={'apply_to_current': args.apply_to_current}, fresh=args.fresh, retry_unresolved=args.retry_unresolved)
        finally:
            await application.close()
    from ..configuration import load_configuration
    # Material-only resolution does not require a benchmark preparation or keys.
    config = load_configuration(workspace, args.config, material_only=True, stage=args.command)
    from fruitfly_agent.run.improvement.roles import ResearchRoles
    from fruitfly_agent.improvement.contracts.plans import RunPlan
    from fruitfly_agent.improvement.contracts.versions import SystemVersion, content_hash
    roles = ResearchRoles(workspace, config.resolve(config.runtime['config']), profile=config.runtime.get('profile'), overrides=config.models)
    from fruitfly_agent.run.improvement.configuration.snapshot import snapshot
    revision = snapshot(config, roles, action=args.command, inputs=args.inputs)
    reporting['source_receipts'] = (*config.source_files, *roles.profile.source_files)
    reporting['configuration'] = revision
    service.revise(revision, direction=config.improvement.direction)
    # Proposal-only bindings describe the currently granted configuration. They
    # are not a reconstructed historical execution or an activation proof.
    configured = roles.profile.to_dict(references=False)
    parent = SystemVersion(*(artifacts.put(canonical_json({'scope': 'configuration-research',
        'axis': axis, 'components': configured[axis],
        **({'runtime': roles.profile.to_runtime_dict()} if axis == 'H' else {})}).encode())
        for axis in ('H', 'I', 'S')))
    service.plan = RunPlan(args.study, parent, config.improvement.components or ('base_prompt',),
        direction=config.improvement.direction, timeouts=config.improvement.timeouts,
        component_options=config.improvement.component_options)
    inputs, producers, named = resolve_inputs(outputs, args)
    reporting.update(inputs=inputs, producers=producers)
    _capture_configuration(outputs, reporting)
    try:
        if args.command == 'organize':
            from fruitfly_agent.lab.improvement.organizer import LayeredOrganizer, OrganizerInstructions
            instructions = roles.profile.component_settings.get('organizer', {}).get('instructions', {})
            service.organizer = LayeredOrganizer(roles.configuration('organizer'), artifacts,
                instructions=OrganizerInstructions(**instructions), settings=config.evidence_settings)
            service.role_identity['organize'] = {'model': roles.identity('organizer'), 'instructions': instructions,
                'evidence': config.evidence_settings}
        elif args.command in {'assess', 'compare'}:
            from fruitfly_agent.lab.improvement.assessment.completed import CompletedAssessmentService
            role_config = roles.configuration('assessor')
            instructions = roles.profile.component_settings.get('evaluator', {})
            service.assessor = lambda services: CompletedAssessmentService(config=role_config, artifacts=artifacts,
                services=services, instructions=instructions, evidence_settings=config.evidence_settings)
            service.role_identity[args.command] = {'model': roles.identity('assessor'), 'instructions': instructions,
                'evidence': config.evidence_settings}
        elif args.command == 'propose':
            from fruitfly_agent.lab.catalog import optimization_grants, optimization_table
            from fruitfly_agent.lab.catalog.research import configuration_targets
            from fruitfly_agent.lab.improvement.components import component_registry
            from fruitfly_agent.lab.improvement.editor import AgentEditor
            from fruitfly_agent.lab.improvement.editor.generators import GeneratorRegistry, AgentGenerator
            from fruitfly_agent.lab.improvement.editor.proposal import ProposalStage
            from fruitfly_agent.run.runtime.assembly import resolve_base_prompt
            from fruitfly_agent.improvement.stages.services import StageServices
            # Load explicit grants through their owning validators, not through a
            # task backend or an alternate component grammar.
            full = load_configuration(workspace, args.config, stage=args.command)
            options = full.improvement.component_options
            if not full.improvement.components:
                options = optimization_grants(roles.profile, roles.catalog)
            if 'research' in yaml.safe_load(full.path.read_text()):
                from fruitfly_agent.run.improvement.configuration import ResearchDocument
                from fruitfly_agent.run.improvement.configuration.resolution import resolve_optimization
                options = resolve_optimization(ResearchDocument(full.path), roles.profile, roles.catalog)
            table = optimization_table(roles.profile, roles.catalog, tuple(options), options)
            reporting['configuration']['optimization_table'] = table
            reporting['configuration']['experiment']['improvement']['components'] = list(options)
            reporting['configuration']['experiment']['improvement']['component_options'] = options
            _capture_configuration(outputs, reporting)
            text, _ = resolve_base_prompt(roles.profile.prompt, DataArtifactStore(workspace / '.fruitfly/artifacts'), contents=roles.profile.artifact_contents)
            def read_artifact(reference):
                if reference in roles.profile.artifact_contents:
                    return roles.profile.artifact_contents[reference]
                return artifacts.read(reference).decode()
            role_config = roles.configuration('editor')
            from dataclasses import replace
            targets = configuration_targets(roles.profile, roles.catalog, options,
                config=replace(role_config, system_prompt=text), artifact_reader=read_artifact, workspace=workspace)
            components = component_registry(targets)
            components.configure(options)
            service.plan = replace(service.plan, component_ids=tuple(options), component_options=options,
                generator_id=full.improvement.generator)
            from fruitfly_agent.lab.improvement.editor.instructions import EditorInstructions
            editor = AgentEditor(role_config, artifacts, components,
                instructions=EditorInstructions(**roles.profile.component_settings.get('editor', {}).get('instructions', {})), settings=config.evidence_settings)
            generators = roles.extensions.bindings().generators
            service.proposal = ProposalStage(generators=generators, components=components)
            service.services_factory = lambda plan: StageServices(plan, edit=editor.edit)
            service.role_identity['propose'] = {'model': roles.identity('editor'), 'instructions': asdict(editor.instructions),
                'grants': options, 'direction': service.plan.direction,
                'generator': service.plan.generator_id, 'extensions': roles.extensions.identities}
            baseline = service.put('baseline.json', components.snapshot().to_dict())
            named = replace(named, harness=baseline)
            inputs = (baseline, *inputs)
            reporting.update(inputs=inputs, profile=roles.profile, catalog=roles.catalog,
                components=components, artifact_reader=read_artifact, model_source=roles.model_path,
                system_source=str(roles.config_path))
        parameters = {'instruction': getattr(args, 'instruction', '')} if args.command == 'organize' else {}
        return await service.perform_named(args.command, named, parameters=parameters, fresh=args.fresh, retry_unresolved=args.retry_unresolved)
    finally:
        await roles.aclose()


async def dispatch(args, workspace):
    """Every independent invocation has an immutable report and portable outputs."""
    from fruitfly_agent.run.storage.research_bundles import ResearchOutputs
    from fruitfly_agent.run.improvement.configuration.snapshot import differences, redact
    from datetime import datetime, timezone
    outputs = ResearchOutputs(workspace, args.study, getattr(args, 'output_root', None))
    if args.command in {'inspect', 'resume', 'fork'}:
        return await _dispatch(args, workspace, outputs, {})
    run_id = args.command + '-' + uuid4().hex
    prefix = 'runs/' + run_id
    reporting = {'run_id': run_id, 'configuration': {'action': args.command}, 'inputs': (), 'producers': []}
    run = {'id': run_id, 'study': args.study, 'action': args.command, 'status': 'running',
        'started_at': datetime.now(timezone.utc).isoformat(), 'branch': getattr(args, 'branch', 'main')}
    outputs.write(prefix + '/run.json', run)
    try:
        result = await _dispatch(args, workspace, outputs, reporting)
        configuration = redact(reporting['configuration'])
        if reporting.get('service') is not None:
            configuration['implementation_source'] = reporting['service'].source_id
        configuration_id = outputs.artifacts.put_bytes(canonical_json(configuration).encode()).artifact_id
        changes = differences(outputs, configuration, reporting.get('producers', ()))
        import yaml
        (outputs.root / prefix / 'configuration').mkdir(parents=True, exist_ok=True)
        (outputs.root / prefix / 'configuration/requested.yaml').write_text(yaml.safe_dump(configuration.get('authored', {}), allow_unicode=True, sort_keys=False))
        outputs.write(prefix + '/configuration/effective.json', configuration)
        outputs.write(prefix + '/configuration/sources.json', configuration.get('sources', []))
        outputs.write(prefix + '/configuration/differences.json', changes)
        bundle, path = outputs.publish(args.command, run_id, result, reporting['inputs'], configuration_id)
        if args.command == 'propose':
            from fruitfly_agent.run.improvement.configuration.snapshot import export_candidates
            try:
                export_candidates(outputs, path.parent, result, reporting)
            except BaseException:
                # A bundle is consumable only after its complete candidate export.
                path.unlink(missing_ok=True)
                raise
        run.update(status='completed', configuration_id=configuration_id, bundle=str(path),
            content_status=result.content_status, outputs=[asdict(r) for r in result.outputs],
            input_producers=reporting.get('producers', []), configuration_differences=changes)
        outputs.write(prefix + '/inputs.json', [asdict(r) for r in reporting['inputs']])
        outputs.write(prefix + '/outputs.json', bundle.to_dict())
        return {**asdict(result), 'run_id': run_id, 'bundle': str(path),
            'report': str(outputs.root / prefix / 'report.json')}
    except BaseException as exc:
        run.update(status='interrupted' if type(exc).__name__ in {'CancelledError', 'KeyboardInterrupt'} else 'failed',
            error={'type': type(exc).__name__, 'message': str(exc)})
        safe = redact(reporting['configuration'])
        outputs.write(prefix + '/configuration/effective.json', safe)
        outputs.write(prefix + '/configuration/sources.json', safe.get('sources', []))
        outputs.write(prefix + '/configuration/differences.json', differences(outputs, safe, reporting.get('producers', ())))
        outputs.write(prefix + '/inputs.json', [asdict(r) for r in reporting['inputs']])
        raise
    finally:
        run['finished_at'] = datetime.now(timezone.utc).isoformat()
        outputs.write(prefix + '/run.json', run)
        outputs.write(prefix + '/report.json', run)
        (outputs.root / prefix / 'report.md').write_text('# Research run ' + run_id + '\n\n```json\n' +
            json.dumps(run, ensure_ascii=False, indent=2) + '\n```\n')
        outputs.write('study.json', {'id': args.study, 'latest_run': run_id,
            'configuration_policy': 'Differences are reported, not restoration gates.'})


def _capture_configuration(outputs, reporting):
    """Commit configuration before a Provider or external task can begin."""
    if 'run_id' not in reporting:
        return
    for source in reporting.get('source_receipts', ()):
        source.check()
    from fruitfly_agent.run.improvement.configuration.snapshot import redact, differences
    import yaml
    prefix = 'runs/' + reporting['run_id'] + '/configuration'
    safe = redact(reporting['configuration'])
    outputs.write(prefix + '/effective.json', safe)
    outputs.write(prefix + '/sources.json', safe.get('sources', []))
    outputs.write(prefix + '/differences.json', differences(outputs, safe, reporting.get('producers', ())))
    if 'optimization_table' in safe:
        from fruitfly_agent.lab.catalog import render_optimization_table
        outputs.write(prefix + '/optimization.json', safe['optimization_table'])
        (outputs.root / prefix / 'optimization.md').write_text(render_optimization_table(safe['optimization_table']))
    (outputs.root / prefix / 'requested.yaml').write_text(yaml.safe_dump(safe.get('authored', {}), allow_unicode=True, sort_keys=False))


def defaults(args, workspace):
    """Preview selected/default owner fields without constructing a Provider."""
    from ..configuration import load_configuration
    from fruitfly_agent.lab.catalog import load_system_config, builtin_catalog, optimization_grants, optimization_table
    from fruitfly_agent.run.extensions import configured_extensions
    config = load_configuration(workspace, args.config, stage='propose')
    path = config.resolve(config.runtime['config'])
    extensions = configured_extensions(path, profile_id=config.runtime.get('profile'))
    catalog = extensions.catalog(builtin_catalog()) if extensions.registrations else builtin_catalog()
    profile = load_system_config(path, catalog=catalog).select(config.runtime.get('profile'))
    grants = config.improvement.component_options if config.improvement.components else optimization_grants(profile, catalog)
    if 'research' in yaml.safe_load(config.path.read_text()):
        from fruitfly_agent.run.improvement.configuration import ResearchDocument
        from fruitfly_agent.run.improvement.configuration.resolution import resolve_optimization
        grants = resolve_optimization(ResearchDocument(config.path), profile, catalog)
    return {'selection': 'explicit' if config.improvement.components else 'default',
        'components': list(grants), 'component_options': grants,
        'optimization_table': optimization_table(profile, catalog, tuple(grants), grants)}
