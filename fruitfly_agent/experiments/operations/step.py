"""Translate the common research document into exactly one stage invocation."""
from pathlib import Path
from types import SimpleNamespace
from fruitfly_agent.run.improvement.context import ResearchContext


async def dispatch(args, workspace):
    path = Path(args.config) if args.config else Path(workspace) / '.fruitfly/improvement.yaml'
    if not path.is_absolute():
        path = Path(workspace) / path
    if args.command in {'inspect', 'resume', 'list', 'report'}:
        from fruitfly_agent.run.improvement.configuration import ResearchDocument
        from .research import dispatch as inspect
        document = ResearchDocument(path)
        if args.command in {'list', 'report'}:
            import json
            if args.command == 'list':
                return [json.loads(report.read_text()) for report in sorted((document.root / 'runs').glob('*/report.json'))]
            from fruitfly_agent.improvement.contracts.validation import identifier
            identifier(args.run_id)
            return json.loads((document.root / 'runs' / args.run_id / 'report.json').read_text())
        return await inspect(SimpleNamespace(command=args.command,
            study=document.research['id'], output_root=str(document.root)), workspace)
    stage = None if args.command in {'step', 'show', 'check', 'inspect', 'resume'} else args.command
    context = ResearchContext.resolve(path, stage)
    if args.command in {'show', 'check'}:
        # Only the selected stage's declared dependencies are checked here.
        if context.stage != 'import':
            from ..configuration import load_configuration
            config = load_configuration(workspace, path, stage=context.stage)
            from fruitfly_agent.lab.catalog import builtin_catalog, load_system_config, configuration_inventory
            from fruitfly_agent.run.extensions import configured_extensions
            system_path = config.resolve(config.runtime['config'])
            extensions = configured_extensions(system_path, profile_id=config.runtime.get('profile'))
            catalog = extensions.catalog(builtin_catalog()) if extensions.registrations else builtin_catalog()
            profile = load_system_config(system_path, catalog=catalog).select(config.runtime.get('profile'))
            if context.stage == 'propose':
                from .research import defaults
                scope = defaults(SimpleNamespace(config=str(path)), workspace)
            else:
                scope = {}
            result = {**context.preview(), 'configuration': config.snapshot(), 'optimization': scope,
                'configuration_table': configuration_inventory(profile, catalog),
                'effective_roles': {**profile.resolved_model_roles(profile.model_profile), **config.models},
                'connectivity': 'not checked'}
            if args.command == 'check' and context.stage in {'execute', 'eval'}:
                from ..composition import prepare_experiment
                prepared = prepare_experiment(config, 'eval' if context.stage == 'eval' else 'improvement',
                    require_prepared=False, require_credentials=False)
                result.update(available=prepared.summary()['available'], execution=prepared.summary())
            return result
        result = context.preview()
        if args.command == 'check':
            source = context.document.resolve(context.settings.get('path', ''))
            available = source.is_file() if context.settings.get('source') == 'batch' else source.is_dir()
            result.update(available=available, source_path=str(source))
            if not available:
                result['unavailable_reason'] = 'Selected import source is missing or has the wrong file type.'
        return result
    inputs = context.inputs
    ordered = []
    if context.stage == 'execute':
        ordered.append(inputs['harness'])
    ordered.extend(inputs.get('batches', []))
    for name in ('evidence', 'assessments', 'context'):
        ordered.extend(inputs.get(name, []))
    attempt = context.settings.get('attempt', 'reuse')
    settings = context.settings
    invocation = SimpleNamespace(command=context.stage, config=str(path),
        study=context.document.research['id'], output_root=str(context.document.root),
        branch=context.branch, inputs=ordered, apply_to_current=False,
        fresh=attempt == 'fresh', retry_unresolved=attempt == 'retry-unresolved',
        source=settings.get('source'), path=str(context.document.resolve(settings['path'])) if 'path' in settings else None,
        related_records=str(context.document.resolve(settings['related_records'])) if settings.get('related_records') else None,
        instruction=settings.get('instruction', ''), task_names=settings.get('task_names', []),
        evidence_paths=settings.get('evidence_paths', {}), named_inputs=inputs,
        harness_bundle=inputs.get('harness_bundle'))
    from .research import dispatch as perform
    result = await perform(invocation, workspace)
    from fruitfly_agent.run.improvement.configuration.presentation import record_result
    return {**result, **record_result(context, result)}
