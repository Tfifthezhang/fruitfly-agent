"""Host component improvement through public Lab ports and frozen previews."""
from __future__ import annotations

from dataclasses import asdict, replace
import json
from pathlib import Path
import asyncio
from fruitfly_agent.improvement.contracts.candidates import CandidateBundle
from typing import Callable
from uuid import uuid4

from fruitfly_agent.improvement.contracts.plans import RunPlan
from fruitfly_agent.lab.improvement.api import ComponentWorkflow, GeneratorRegistry, AgentGenerator, AgentComposer, AgentEditor, AgentSelector, AgentReflector, component_registry, experience_id, SearchActivity, SearchCompletion, model_completion, ExecutionContext, builtin_executions, bundle_target, bundle_text, ReadOnlyInspector, policy_spec, builtin_strategies, ExplorationSettings, builtin_explorations, validate_exploration, CompletedAssessmentService, exploration_settings, install_workflow_mechanisms, extension_spec, evaluator_instructions, organize_evidence
from fruitfly_agent.improvement.workflow.services import WorkflowServices
from fruitfly_agent.improvement.evidence.reporting import SearchReport
from fruitfly_agent.improvement.contracts.editing import EvidenceInspector
from fruitfly_agent.improvement.contracts.experiments import ExecutionRequest
from fruitfly_agent.improvement.contracts.components import HarnessSnapshot
from fruitfly_agent.improvement.contracts.validation import relative_path
from fruitfly_agent.improvement.contracts.versions import SystemVersion, content_hash, canonical_json
from fruitfly_agent.rsi.contracts import VerificationEvidence
from fruitfly_agent.interactive.contracts.improvement import (WorkflowConfiguration,
    WorkflowChoice, WorkflowComponentView, ImprovementParameterView, ImprovementPreview, WorkflowExecutionView)
from fruitfly_agent.run.storage.verification import VerificationUseStore
from fruitfly_agent.interactive.contracts.experience import PendingExperienceView
from .results import material_details, result_view


class ArtifactPort:
    def __init__(self, store):
        self.store = store

    def put(self, content):
        return self.store.put_bytes(content).artifact_id

    def read(self, reference):
        return self.store.read_bytes(reference)


class RunComponentJobs:
    """No algorithm dispatch: injected factories implement the public stage ports."""
    def __init__(self, *, workspace, artifacts, experience, manifest, version, config,
                 targets, generators=None, runner=None, composer=None, selector=None,
                 reflector=None, verifier=None, measurements=None, workflow_factory=None,
                 tasks=None, publish=None, editor=None, inspector=None, components=None, executions=None, stop_policy=None, strategies=None,
                 exploration=None, explorations=None, component_options=None, hooks=None, delivery_backend=None, workflow_settings=None, evidence_settings=None):
        self.workflow_settings = dict(workflow_settings or {})
        self.evidence_settings = dict(evidence_settings or {})
        self.component_options = json.loads(json.dumps(component_options or {}, allow_nan=False))
        self.workspace, self.artifacts = Path(workspace), ArtifactPort(artifacts)
        self.experience, self.manifest, self.version = experience, manifest, version
        self.config, self.targets = config, targets
        self.generators = generators or GeneratorRegistry()
        if generators is None:
            self.generators.register(AgentGenerator.generator_id, AgentGenerator)
        self.runner_factory, self.composer_factory, self.selector_factory = runner, composer, selector
        self.reflector_factory, self.verifier, self.measurements = reflector, verifier, measurements
        self.controller_factory = workflow_factory or ComponentWorkflow
        self.editor_factory = editor or AgentEditor
        self.inspector_factory = inspector
        self.component_factory = components or component_registry
        self.editor_instructions = lambda: None
        self.editor_configuration = config
        self.assessor_configuration = None
        self.strategies = strategies or builtin_strategies()
        self.defaults: Callable[[], dict] = lambda: {}
        self.system_settings: Callable[[], dict] = lambda: {}
        self.prepare_materialization = None
        self.tasks, self.publish = tasks, publish
        self.executions = executions or builtin_executions()
        self.stop_policy = stop_policy
        self.hooks_factory = hooks
        self.delivery_backend = delivery_backend
        self.exploration_settings = exploration
        self.explorations = explorations or builtin_explorations()
        if exploration is not None:
            validate_exploration(exploration, self.explorations)
        self.verification_uses = VerificationUseStore(self.workspace / '.fruitfly/improvement/verification-uses.json')
        self.previews = {}
        self.services = None
        self.outcome = None
        self._completion = None
        self.running_improver = None
        self.observed_usage = {'model': 0, 'execution': 0}
    def registry(self):
        registry = self.component_factory(tuple(self.targets()))
        registry.configure(self.component_options)
        return registry

    def identity(self, *, system_settings=None):
        values = self.system_settings() if system_settings is None else system_settings
        exploration = self.exploration_configuration(values)
        def identity(value, default):
            return getattr(value, 'implementation_id',
                getattr(value, '__module__', type(value).__module__) + '.' +
                getattr(value, '__qualname__', type(value).__qualname__)) if value is not None else default
        return {'workflow': 'component-search-v1',
                **({'system_settings': values} if values else {}),
                'strategies': [(d.strategy_id, d.implementation_id) for d in self.strategies.definitions()],
                'executions': [(d.execution_id, d.implementation_id) for d in self.executions.definitions()],
                'generators': tuple(asdict(d) | {'required_capabilities': sorted(d.required_capabilities)} for d in self.generators.definitions()),
                'stages': {name: identity(value, default) for name, value, default in (
                    ('editor', self.editor_factory, 'workspace-editor-v1'),
                    ('inspector', self.inspector_factory, 'workspace-inspector-v1'),
                    ('compose', self.composer_factory, 'agent-composer-v1'),
                    ('select', self.selector_factory, 'agent-selector-v1'),
                    ('reflect', self.reflector_factory, 'agent-reflector-v1'),
                    ('workflow', self.controller_factory, 'component-search-v1'))},
                'stop_policy': policy_spec(self.stop_policy),
                'hooks': extension_spec(self.hooks_factory),
                'delivery_backend': extension_spec(self.delivery_backend),
                'component_options': self.component_options,
                'workflow_settings': self.workflow_settings, 'evidence_settings': self.evidence_settings,
                'exploration': {**asdict(exploration),
                    'implementation_id': self.explorations.get(exploration.policy).implementation_id}}

    def exploration_configuration(self, values=None):
        value = self.exploration_settings or exploration_settings(self.system_settings() if values is None else values)
        validate_exploration(value, self.explorations)
        return value

    def completed_assessment(self, services):
        return CompletedAssessmentService(config=self.assessor_configuration() if self.assessor_configuration else self.editor_configuration(),
            artifacts=self.artifacts, services=services,
            instructions=self.system_settings().get('evaluator', {}), evidence_settings=self.evidence_settings)

    def exploration_policy(self, services):
        return self.explorations.create(self.exploration_configuration().policy, own=services.own)

    def context(self, plan=None, services=None, experience=()):
        return ExecutionContext(self.workspace, self.artifacts, self.registry(),
            self.tasks() if self.tasks is not None else None, self.config(), self.editor_configuration(),
            experience=experience, plan=plan, services=services, runner_factory=self.runner_factory,
            measurements=self.measurements, verifier=self.verifier, claim_verification=self.verification_uses.claim,
            remaining_verification=self.verification_uses.remaining,
            assessor_config=self.assessor_configuration() if self.assessor_configuration else self.editor_configuration(),
            completed_assessment_factory=self.completed_assessment, exploration_factory=self.exploration_policy,
            generator_definitions=self.generators.definitions(), system_settings=self.system_settings(), workflow_settings=self.workflow_settings, evidence_settings=self.evidence_settings, hooks_factory=self.hooks_factory, delivery_backend=self.delivery_backend)

    def workflow_configuration(self):
        context = self.context()
        views = []
        documents = context.components.snapshot().components
        for definition in self.executions.definitions():
            capabilities = (getattr(self.runner_factory, 'capabilities', definition.capabilities)
                if definition.accepts_runner_override and self.runner_factory else definition.capabilities_for(t.name for t in context.config.tools))
            ids = tuple(d.component_id for d in documents if d.role in definition.roles and not (
                getattr(context.components.adapters[d.component_id], 'required_capabilities', frozenset()) - capabilities))
            sources = definition.materials(context)
            views.append(WorkflowExecutionView(definition.execution_id, definition.label, ids,
                tuple(WorkflowChoice(v.material_id, v.label, not v.error, v.error, v.detail) for v in sources),
                tuple(ImprovementParameterView(p.name, p.label, p.kind, p.default, p.minimum, p.maximum,
                    'execution', p.description) for p in definition.parameters), definition.notice, definition.defaults))
        primary = views[0]
        components = tuple(WorkflowComponentView(d.component_id,
            getattr(getattr(context.components.adapters[d.component_id], 'target', None), 'label', d.component_id),
            d.kind, d.role, d.component_id in primary.component_ids,
            '' if d.component_id in primary.component_ids else 'Choose an execution strategy supporting this component.') for d in documents)
        measured = self.measurements is not None or any(c.choice_id and c.available for v in views for c in v.materials)
        generators = tuple(WorkflowChoice(d.generator_id, d.label,
            not (d.required_capabilities - ({'editor', 'model'} | ({'measurements'} if measured else set()))),
            'Required capabilities are not available.' if d.required_capabilities - ({'editor', 'model'} | ({'measurements'} if measured else set())) else '')
            for d in self.generators.definitions())
        return WorkflowConfiguration(components, generators,
            (WorkflowChoice('parallel', 'Parallel exploration'), WorkflowChoice('sequential', 'Sequential refinement')),
            (WorkflowChoice('behavior', 'Execution evidence', detail='Selection is not proof of quality.'),
             WorkflowChoice('scored', 'Measured feedback', measured, '' if measured else 'No measurement source is registered.')),
            (WorkflowChoice('task', 'Current task only'), WorkflowChoice('persistent', 'Publish a persistent candidate',
             self.publish is not None, '' if self.publish else 'Publication is unavailable.')),
            tuple(ImprovementParameterView(name, label, kind, self.defaults().get(name, default), low, high, 'timing' if name.endswith('_seconds') else 'search', description)
                for name, label, kind, default, low, high, description in (
                    ('width', 'Exploration width', 'integer', 1, 1, 10, 'Independent proposals per diagnostic scope.'),
                    ('depth', 'Refinement depth', 'integer', 1, 1, 10, 'Successive rounds; only selected incumbents advance.'),
                    ('editor_seconds', 'Editor time', 'number', 1200, 0, None, 'Independent seconds for one editing invocation.'),
                    ('execution_seconds', 'Execution time', 'number', 3600, 0, None, 'Independent seconds for one task execution.'),
                    ('evaluator_seconds', 'Evaluator time', 'number', 1200, 0, None, 'Independent seconds for one assessment or comparison.'))),
            primary.materials, tuple(views))

    def preview(self, request, *, material=None):
        if material is not None:
            raise ValueError('external materials require a registered execution source')
        options = self.workflow_configuration()
        definition = self.executions.get(request.execution_id)
        view = next(v for v in options.executions if v.execution_id == request.execution_id)
        if not request.component_ids:
            component_ids = view.component_ids
            if definition.component_scope is not None:
                component_ids = definition.component_scope(self.context(), request.task_pack_id, component_ids)
            request = replace(request, component_ids=component_ids)
        if not request.component_ids or set(request.component_ids) - set(view.component_ids):
            raise ValueError('select available editable components for this execution strategy')
        for selected, choices in ((request.generator_id, options.generators), (request.mode, options.modes),
                                  (request.verification, options.verification), (request.scope, options.scopes)):
            if not any(c.choice_id == selected and c.available for c in choices):
                raise ValueError('selected workflow capability is unavailable')
        parameters = tuple(sorted(definition.normalize(request.execution_parameters).items()))
        plan = definition.plan_factory('job-' + uuid4().hex, self.version(), request.component_ids, request.generator_id,
            request.mode, request.width, request.depth, request.scope, request.verification,
            timeouts=request.timeouts, direction=request.direction)
        plan = replace(plan, strategy_id=request.strategy_id, retain_experience=request.retain_experience,
            component_options=self.component_options)
        self.strategies.get(plan.strategy_id).schedule(plan)
        experience = self.experience.snapshot()
        context = self.context(plan, experience=experience)
        plan = replace(plan, component_description_id=content_hash(canonical_json(
            context.components.descriptions(plan.component_ids))))
        context.plan = plan
        execution_request = ExecutionRequest(request.instruction, request.input_paths,
            request.component_ids, request.task_pack_id, request.scope, request.verification, parameters)
        prepared = definition.prepare(context, execution_request)
        token = uuid4().hex
        if len(self.previews) >= 16:
            self.previews.pop(next(iter(self.previews)))
        self.previews[token] = (plan, prepared, context.components.snapshot(), context.components, experience,
                               self.manifest()['digest'], definition, execution_request)
        return ImprovementPreview(plan.generator_id, 'Component improvement', definition.notice,
            (*material_details(prepared.task),
             ('Components', ', '.join(plan.component_ids)), ('Candidate generator', plan.generator_id),
             ('Execution strategy', definition.label), ('Material identity', prepared.source_id),
             ('Execution parameters', json.dumps(dict(parameters), ensure_ascii=False)),
             ('Search strategy', plan.strategy_id),
             ('Exploration', f'{plan.mode}; width={plan.width}; depth={plan.depth}'),
             ('Feedback', plan.feedback), ('Effect scope', plan.purpose),
             ('Stage times', json.dumps(asdict(plan.timeouts))),
             ('Experience snapshot', experience_id(experience)),
             ('Feedback assurance', 'Development signals do not grant independent verification.'),
             *prepared.details), target='component-bundle', preview_token=token,
             role=context.components.snapshot().component(plan.component_ids[0]).role)

    async def improve(self, manifest, direction, *, preview_token):
        self._completion, self.outcome = None, None
        if preview_token not in self.previews:
            raise ValueError('unknown or consumed component preview')
        plan, prepared, baseline, registry, experience, digest, definition, execution_request = self.previews.pop(preview_token)
        task = prepared.task
        if (manifest['digest'] != digest or self.manifest()['digest'] != digest or self.version() != plan.parent
                or direction != plan.direction or self.registry().snapshot() != baseline
                or experience_id(self.experience.snapshot()) != experience_id(experience)
                or prepared.current_source() != prepared.source_id):
            raise ValueError('task improvement conditions changed; preview again')
        if content_hash(canonical_json(self.registry().descriptions(plan.component_ids))) != plan.component_description_id:
            raise ValueError('component descriptions changed; preview again')
        root = self.workspace / '.fruitfly/improvement/jobs' / plan.job_id
        if not root.resolve().is_relative_to(self.workspace.resolve()):
            raise ValueError('job records must remain inside the workspace')
        root.mkdir(parents=True, exist_ok=False)
        (root / 'plan.json').write_text(json.dumps({'schema_version': 2, 'plan': asdict(plan),
            'task': asdict(task), 'baseline': baseline.to_dict(), 'experience': experience_id(experience),
            'execution': {'id': definition.execution_id, 'implementation': definition.implementation_id,
                          'source_id': prepared.source_id, 'details': prepared.details,
                          'request': asdict(execution_request)}}, ensure_ascii=False), encoding='utf-8')
        materialize = self.prepare_materialization(root) if self.prepare_materialization else None
        materialized = set()
        stream = (root / 'events.jsonl').open('x', encoding='utf-8')
        def record(event, **fields):
            stream.write(json.dumps({'event': event, **fields}, ensure_ascii=False) + '\n')
            stream.flush()
            if event == 'workflow-checkpoint':
                path = root / 'checkpoint.json'
                temporary = root / 'checkpoint.tmp'
                temporary.write_text(json.dumps(fields['outcome'], ensure_ascii=False, allow_nan=False), encoding='utf-8')
                temporary.replace(path)
            elif event == 'candidate-validated' and materialize is not None:
                candidate = CandidateBundle.from_dict(fields['candidate'])
                if candidate.candidate_id not in materialized:
                    destination = root / 'candidates' / candidate.candidate_id.removeprefix('sha256:')
                    path = materialize(candidate, registry, destination)
                    materialized.add(candidate.candidate_id)
                    stream.write(json.dumps({'event': 'candidate-configuration', 'candidate_id': candidate.candidate_id,
                        'config': str(path.relative_to(self.workspace)), 'conditions_id': plan.conditions_id}) + '\n')
                    stream.flush()
        services = WorkflowServices(plan, record=record)
        services.evidence_builder = organize_evidence
        self.services, self.running_improver, self.outcome = services, self, None
        self._completion = None
        stop = 'error'
        try:
            services.completer = model_completion(self.editor_configuration())
            if self.editor_factory is AgentEditor:
                editor = self.editor_factory(self.editor_configuration(), self.artifacts, registry,
                    instructions=self.editor_instructions(),
                    page_characters=self.evidence_settings.get('page_characters', 12000))
            else:
                editor = self.editor_factory(self.editor_configuration(), self.artifacts, registry)
            services.own(editor)
            services.editor = editor.edit
            assessment_config = self.assessor_configuration() if self.assessor_configuration is not None else self.editor_configuration()
            inspector = (self.inspector_factory(assessment_config, self.artifacts, registry)
                if self.inspector_factory is not None
                else ReadOnlyInspector(assessment_config, self.artifacts, registry,
                                 instructions=self.editor_instructions(),
                                 evaluator_instructions=evaluator_instructions(self.system_settings()), evidence_settings=self.evidence_settings))
            services.own(inspector)
            context = self.context(plan, services, experience)
            context.components = registry
            context.component_ids = plan.component_ids
            def save_record(relative, value):
                relative_path(relative)
                path = root / relative
                if not path.resolve().is_relative_to(root.resolve()) or any(
                        p.is_symlink() for p in (path, *path.parents) if p.is_relative_to(root)):
                    raise ValueError('job records must remain inside their owned directory without symlinks')
                path.parent.mkdir(parents=True, exist_ok=True)
                data = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)
                if path.exists():
                    if path.read_text() != data:
                        raise ValueError('immutable job record changed')
                else:
                    with path.open('x', encoding='utf-8') as target:
                        target.write(data)
            context.save_record = save_record
            ports = definition.build(context, prepared)
            runner = services.own(ports.runner)
            stop_policy = install_workflow_mechanisms(context, stop_policy=self.stop_policy)
            composer = self.composer_factory(plan, services) if self.composer_factory else AgentComposer()
            services.own(composer)
            selector = self.selector_factory(plan, services) if self.selector_factory else ports.selector or AgentSelector(inspector, services)
            services.own(selector)
            reflector = (self.reflector_factory(plan, services) if self.reflector_factory else AgentReflector(inspector, services)) if plan.retain_experience else None
            services.own(reflector)
            measurements, verifier = ports.measurements, ports.verifier
            completed_assessment = self.completed_assessment(services)
            workflow = self.controller_factory(generators=self.generators, components=registry,
                runner=runner, composer=composer, selector=selector, reflector=reflector,
                measurements=measurements, verifier=verifier,
                artifacts=self.artifacts, completed_assessment=completed_assessment,
                exploration=self.exploration_policy(services),
                **({'problem': ports.search_problem} if ports.search_problem is not None else {}),
                **({"strategies": self.strategies} if self.controller_factory is ComponentWorkflow else {}),
                **({"stop_policy": stop_policy} if self.controller_factory is ComponentWorkflow or self.stop_policy is not None else {}))
            services.own(workflow)
            outcome = await workflow.run(plan, task, baseline, services, experience=experience)
            services.check()
            if self.version() != plan.parent:
                raise ValueError('production H/I/S changed during task improvement')
            proof = getattr(verifier, 'receipt', None)
            if outcome.decision is not None and outcome.decision.assurance == 'verified' and proof:
                reference = self.artifacts.put(json.dumps({'schema_version': 1,
                    'policy_id': verifier.policy_id, 'execution_id': definition.execution_id,
                    'implementation_id': definition.implementation_id, 'source_id': prepared.source_id,
                    'request': asdict(execution_request), 'plan': asdict(plan),
                    'harness': outcome.harness.to_dict(), 'evidence': proof}, sort_keys=True).encode())
                outcome = replace(outcome, verification=reference)
            self.outcome = outcome
            if materialize is not None:
                for candidate in {c.candidate_id: c for c in outcome.candidates}.values():
                    if candidate.candidate_id in materialized:
                        continue
                    destination = root / 'candidates' / candidate.candidate_id.removeprefix('sha256:')
                    path = materialize(candidate, registry, destination)
                    record('candidate-configuration', candidate_id=candidate.candidate_id,
                           config=str(path.relative_to(self.workspace)), conditions_id=plan.conditions_id)
            stop = outcome.stop_reason
            services.record('workflow-completed', stop_reason=stop,
                selected=result_view(outcome)['id'] or None,
                assurance=outcome.decision.assurance if outcome.decision else 'unavailable')
            (root / 'result.json').write_text(json.dumps(asdict(outcome), ensure_ascii=False), encoding='utf-8')
            if outcome.experience and plan.purpose == 'task' and ports.retain_experience:
                self.experience.stage(plan.job_id, outcome.experience, expected_snapshot=experience_id(experience))
                record('experience-pending', job_id=plan.job_id, initial_snapshot=experience_id(experience))
            if (plan.purpose == 'persistent' and outcome.decision is not None
                    and outcome.decision.assurance == 'verified'):
                return self.publish(outcome, baseline, tuple(registry.adapters.values()))
            return ()
        except asyncio.CancelledError:
            stop = 'cancelled'
            services.record('workflow-interrupted', stop_reason=stop)
            raise
        except Exception as exc:
            services.record('workflow-interrupted', stop_reason=stop, error=type(exc).__name__)
            raise
        finally:
            for kind, amount in services.used.items():
                self.observed_usage[kind] += amount
            try:
                await services.close()
            finally:
                self.running_improver, self.services = None, None
                stream.close()
            view = result_view(self.outcome)
            from fruitfly_agent.improvement.evidence.reporting import token_usage
            rows = [{**row, 'kind': row['event']}
                    for row in (json.loads(line) for line in (root / 'events.jsonl').read_text().splitlines())]
            self._completion = SearchCompletion(SearchReport(stop_reason=stop,
                tokens=token_usage(rows, services.used['model']),
                model_calls=services.used['model'], trial_calls=services.used['execution']),
                (('Component job', str(root.relative_to(self.workspace))),
                 ('Assurance', self.outcome.decision.assurance if self.outcome and self.outcome.decision else 'unavailable'),
                 *(((view['label'], view['id']),) if view['id'] else ()),
                 *((('Exploration seed', view['exploration']),) if view['exploration'] else ()),
                 *view['evidence']),
                summary=('Persistent candidate verification finished; review the result before adoption.'
                         if plan.purpose == 'persistent' else 'Current-task refinement finished; profile defaults are unchanged.'),
                output=view['output'],
                assurance=self.outcome.decision.assurance if self.outcome and self.outcome.decision else 'unavailable')
            self.running_improver, self.services = None, None
            stream.close()
            journal = (root / 'events.jsonl').read_bytes()
            from hashlib import sha256
            self._completion = replace(self._completion, evidence=(*self._completion.evidence,
                ('Workflow journal', str((root / 'events.jsonl').relative_to(self.workspace))),
                ('Workflow journal hash', 'sha256:' + sha256(journal).hexdigest())))

    def completion(self):
        return self._completion

    def pending_experience(self):
        return tuple(PendingExperienceView(v['job_id'], v['initial_snapshot'],
            tuple(e['lesson'] for e in v['entries']),
            tuple((e['task_id'], 'Cue: ' + e['cue'] + '\nEvidence: ' + ', '.join(e['evidence_ids']) +
                   '\nLimits: ' + e['limitations']) for e in v['entries'])) for v in self.experience.pending())

    def experience_action(self, job_id, action):
        return self.experience.review(job_id, action)

    def verified_candidate(self, record, policy_id):
        reference = dict(record.evidence).get('Verification receipt')
        if not reference:
            raise ValueError('candidate has no reusable independent verification receipt')
        value = json.loads(self.artifacts.read(reference))
        if value.get('schema_version') != 1 or value.get('policy_id') != policy_id:
            raise ValueError('verification policy or receipt schema mismatch')
        plan_value = dict(value['plan'])
        plan_value['parent'] = SystemVersion(**plan_value['parent'])
        plan = RunPlan(**plan_value)
        if plan.parent != self.version() or record.parent_manifest_digest != self.manifest()['digest']:
            raise ValueError('verification parent or conditions changed')
        definition = self.executions.get(value['execution_id'])
        if definition.implementation_id != value['implementation_id']:
            raise ValueError('verification implementation changed')
        request_value = dict(value['request'])
        for name in ('input_paths', 'component_ids', 'parameters'):
            request_value[name] = tuple(tuple(v) if isinstance(v, list) else v for v in request_value[name])
        context = self.context(plan, experience=self.experience.snapshot())
        # A completed proof consumes no new private-suite use or model work.
        context.remaining_verification = None
        prepared = definition.prepare(context, ExecutionRequest(**request_value))
        if prepared.source_id != value['source_id']:
            raise ValueError('verification material changed')
        target = bundle_target(tuple(self.targets()))
        text = bundle_text(target, HarnessSnapshot.from_dict(value['harness']))
        if content_hash(text) != record.artifact_id:
            raise ValueError('verification candidate content mismatch')
        self.artifacts.read(value['evidence'])
        return VerificationEvidence(record.candidate_id, record.artifact_id, record.parent_manifest_digest,
                                    policy_id, True, 'Reused exact completed independent verification: ' + reference)

    def progress(self):
        if self.services is None:
            return None
        used, plan = self.services.used, self.services.plan
        phase = self.services.events[-1][0] if self.services.events else 'Preparing task'
        return SearchActivity(phase, model_calls=used['model'], trial_calls=used['execution'])

    def cancel(self):
        if self.services is None:
            return False
        self.services.signal.set()
        return True
