"""Host component improvement through public Lab ports and frozen previews."""
from __future__ import annotations

from dataclasses import asdict, replace
import json
from pathlib import Path
import asyncio
from fruitfly_agent.improvement.contracts.candidates import CandidateBundle
from typing import Callable, Any
from uuid import uuid4

from fruitfly_agent.improvement.contracts.plans import RunPlan
from fruitfly_agent.lab.catalog import registry_optimization_table, render_optimization_table, select_default_components
from fruitfly_agent.lab.improvement.api import GeneratorRegistry, AgentGenerator, AgentEditor, AgentSelector, AgentReflector, component_registry, experience_id, SearchActivity, SearchCompletion, model_completion, ExecutionContext, builtin_executions, bundle_target, bundle_text, ReadOnlyInspector, policy_spec, CompletedAssessmentService, extension_spec, evaluator_instructions, organize_evidence
from fruitfly_agent.improvement.stages.services import StageServices
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


from fruitfly_agent.run.storage.research_bundles import ArtifactPort


class RunExecutionHost:
    """No algorithm dispatch: injected factories implement the public stage ports."""
    def __init__(self, *, workspace, artifacts, experience, manifest, version, config,
                 targets, generators=None, runner=None,
                 verifier=None, measurements=None,
                 tasks=None, publish=None, editor=None, components=None, executions=None,
                 component_options=None, hooks=None, delivery_backend=None, evidence_settings=None,
                 resource_factories=None, organizer=None, evidence_selector=None):
        self.evidence_selector_factory = evidence_selector
        self.resource_factories: Callable[[], dict[str, Any]] = resource_factories or (lambda: {})
        self.evidence_settings = dict(evidence_settings or {})
        self.component_options = json.loads(json.dumps(component_options or {}, allow_nan=False))
        self.workspace, self.artifacts = Path(workspace), ArtifactPort(artifacts)
        self.experience, self.manifest, self.version = experience, manifest, version
        self.config, self.targets = config, targets
        self.generators = generators or GeneratorRegistry()
        if generators is None:
            self.generators.register(AgentGenerator.generator_id, AgentGenerator)
        self.runner_factory = runner
        self.verifier, self.measurements = verifier, measurements
        
        self.editor_factory = editor or AgentEditor
        self.component_factory = components or component_registry
        self.editor_instructions = lambda: None
        self.editor_configuration = config
        self.assessor_configuration = None
        self.organizer_configuration = None
        from fruitfly_agent.lab.improvement.api import LayeredOrganizer
        self.organizer_factory = organizer or LayeredOrganizer
        self.defaults: Callable[[], dict] = lambda: {}
        self.system_settings: Callable[[], dict] = lambda: {}
        self.prepare_materialization = None
        self.tasks, self.publish = tasks, publish
        self.executions = executions or builtin_executions()
        self.hooks_factory = hooks
        self.delivery_backend = delivery_backend
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
        def identity(value, default):
            return getattr(value, 'implementation_id',
                getattr(value, '__module__', type(value).__module__) + '.' +
                getattr(value, '__qualname__', type(value).__qualname__)) if value is not None else default
        return {'execution_mode': 'independent-research-v1',
                **({'system_settings': values} if values else {}),
                'executions': [(d.execution_id, d.implementation_id) for d in self.executions.definitions()],
                'generators': tuple(asdict(d) | {'required_capabilities': sorted(d.required_capabilities)} for d in self.generators.definitions()),
                'stages': {name: identity(value, default) for name, value, default in (
                    ('editor', self.editor_factory, 'workspace-editor-v1'),
                    ('execution', self.runner_factory, 'registered-execution-v1'))},
                'hooks': extension_spec(self.hooks_factory),
                'delivery_backend': extension_spec(self.delivery_backend),
                'component_options': self.component_options,
                'evidence_settings': self.evidence_settings}


    def completed_assessment(self, services):
        return CompletedAssessmentService(config=self.assessor_configuration() if self.assessor_configuration else self.editor_configuration(),
            artifacts=self.artifacts, services=services,
            instructions=self.system_settings().get('evaluator', {}), evidence_settings=self.evidence_settings)


    def context(self, plan=None, services=None, experience=()):
        return ExecutionContext(self.workspace, self.artifacts, self.registry(),
            self.tasks() if self.tasks is not None else None, self.config(), self.editor_configuration(),
            experience=experience, plan=plan, services=services, runner_factory=self.runner_factory,
            measurements=self.measurements, verifier=self.verifier, claim_verification=self.verification_uses.claim,
            remaining_verification=self.verification_uses.remaining,
            organizer_factory=self.organizer_factory,
            organizer_config=self.organizer_configuration() if self.organizer_configuration else self.editor_configuration(),
            assessor_config=self.assessor_configuration() if self.assessor_configuration else self.editor_configuration(),
            completed_assessment_factory=self.completed_assessment,
            generator_definitions=self.generators.definitions(), system_settings=self.system_settings(), evidence_settings=self.evidence_settings, hooks_factory=self.hooks_factory, delivery_backend=self.delivery_backend,
            resource_factories=dict(self.resource_factories()))

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
        inventory = (self.manifest() or {}).get('harness', {})
        owners = dict(inventory.get('owners', ()))
        coordinates = {row['component_id']: tuple(row.get('feature_path', ()))
                       for row in inventory.get('components', ())}
        components = tuple(WorkflowComponentView(d.component_id,
            getattr(getattr(context.components.adapters[d.component_id], 'target', None), 'label', d.component_id),
            d.kind, d.role, d.component_id in primary.component_ids,
            '' if d.component_id in primary.component_ids else 'Choose an execution strategy supporting this component.',
            owners.get(d.component_id, ''), coordinates.get(d.component_id, ())) for d in documents)
        measured = self.measurements is not None or any(c.choice_id and c.available for v in views for c in v.materials)
        generators = tuple(WorkflowChoice(d.generator_id, d.label,
            not (d.required_capabilities - ({'editor', 'model'} | ({'measurements'} if measured else set()))),
            'Required capabilities are not available.' if d.required_capabilities - ({'editor', 'model'} | ({'measurements'} if measured else set())) else '')
            for d in self.generators.definitions())
        return WorkflowConfiguration(components, generators,
            (WorkflowChoice('task', 'Current task only'), WorkflowChoice('persistent', 'Publish a persistent candidate',
             self.publish is not None, '' if self.publish else 'Publication is unavailable.')),
            tuple(ImprovementParameterView(name, label, kind, self.defaults().get(name, default), low, high, 'timing' if name.endswith('_seconds') else 'search', description)
                for name, label, kind, default, low, high, description in (
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
            registry = self.context().components
            component_ids = select_default_components({name: registry.adapters[name].optimization for name in view.component_ids})
            if definition.component_scope is not None:
                component_ids = definition.component_scope(self.context(), request.task_pack_id, component_ids)
            request = replace(request, component_ids=component_ids)
        if not request.component_ids or set(request.component_ids) - set(view.component_ids):
            raise ValueError('select available editable components for this execution strategy')
        for selected, choices in ((request.generator_id, options.generators), (request.scope, options.scopes)):
            if not any(c.choice_id == selected and c.available for c in choices):
                raise ValueError('selected workflow capability is unavailable')
        parameters = tuple(sorted(definition.normalize(request.execution_parameters).items()))
        plan = definition.plan_factory('job-' + uuid4().hex, self.version(), request.component_ids, request.generator_id,
            rounds=request.rounds, purpose=request.scope, timeouts=request.timeouts, direction=request.direction)
        plan = replace(plan, retain_experience=request.retain_experience,
            component_options=self.component_options)
        experience = self.experience.snapshot()
        context = self.context(plan, experience=experience)
        plan = replace(plan, component_description_id=content_hash(canonical_json(
            context.components.descriptions(plan.component_ids))))
        context.plan = plan
        execution_request = ExecutionRequest(request.instruction, request.input_paths,
            request.component_ids, request.task_pack_id, request.scope, parameters)
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
             ('Effect scope', plan.purpose),
             ('Stage times', json.dumps(asdict(plan.timeouts))),
             ('Experience snapshot', experience_id(experience)),
             ('Feedback assurance', 'Development signals do not grant independent verification.'),
             *prepared.details), target='component-bundle', preview_token=token,
             role=context.components.snapshot().component(plan.component_ids[0]).role)

    def research_service(self, research_id, request, *, artifacts=None):
        """Compose independent research stages from a registered execution definition."""
        from .service import ResearchService
        from fruitfly_agent.improvement.contracts.research import ResearchBatch
        preview = self.preview(request)
        plan, prepared, baseline, registry, experience, _, definition, _ = self.previews.pop(preview.preview_token)
        plan = replace(plan, job_id=research_id)
        research_artifacts = artifacts or self.artifacts
        def make_services(current):
            services = StageServices(current)
            services.evidence_builder = organize_evidence
            return services
        async def execute(spec, inputs, services):
            if prepared.current_source() != prepared.source_id:
                raise ValueError('execution source changed; prepare the current revision again')
            value = json.loads(research_artifacts.read(inputs.harness.artifact_id))
            harness = baseline
            if 'candidates' in value:
                if len(value['candidates']) != 1:
                    raise ValueError('execution requires exactly one candidate')
                candidate = CandidateBundle.from_dict(value['candidates'][0])
                if candidate.base != baseline:
                    services.record('research-configuration-difference', base_id=candidate.base.snapshot_id, current_id=baseline.snapshot_id)
                    if spec.parameters.get('apply_to_current'):
                        changed = {c.component_id: c for c in candidate.harness.components if c.component_id in candidate.changed_ids}
                        if set(changed) - {c.component_id for c in baseline.components}:
                            raise ValueError('candidate modifies a component unavailable in the current configuration')
                        harness = HarnessSnapshot(tuple(changed.get(c.component_id, c) for c in baseline.components))
                        derived = CandidateBundle(plan.parent, baseline, harness, candidate.generator_id, candidate.reasons)
                        services.record('research-derived-candidate', original=candidate.candidate_id, candidate=asdict(derived))
                    else:
                        harness = candidate.harness
                else:
                    harness = candidate.harness
                if set(candidate.changed_ids) - set(plan.component_ids):
                    raise ValueError('research candidate changes fields outside the current task grant')
                harness = registry.normalize_execution(harness)
            elif 'components' in value:
                harness = HarnessSnapshot.from_dict(value)
                harness = registry.normalize_execution(harness)
            context = self.context(plan, services, experience)
            context.components = registry
            context.artifacts = research_artifacts
            ports = definition.build(context, prepared)
            if ports.execute_batch is not None:
                return await ports.execute_batch(plan, harness, services)
            runner = services.own(ports.runner)
            if runner is None:
                raise ValueError('registered backend exposes no research executor')
            record = await runner.execute(plan, prepared.task, harness)
            record = services.prepare_evidence(prepared.task, record, research_artifacts)
            observations: tuple[dict, ...] = ()
            if ports.measurements is not None:
                measurement = await ports.measurements.measure(prepared.task, record)
                observations = (asdict(measurement),) if measurement else ()
            return ResearchBatch((prepared.task,), (record,), observations)
        return ResearchService(self.workspace, research_id, research_artifacts, plan=plan, harness=baseline,
            executor=execute, services_factory=make_services,
            evidence_selector=(self.evidence_selector_factory(self.system_settings())
                if self.evidence_selector_factory else None),
            role_identity={'execute': {'source': prepared.source_id,
                'execution': definition.implementation_id, 'parent_state': plan.parent.state,
                'timeouts': plan.timeouts.execution_seconds}})

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
