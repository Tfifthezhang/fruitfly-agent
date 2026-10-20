"""Host component improvement through public Lab ports and frozen previews."""
from __future__ import annotations

from dataclasses import asdict, replace
import json
from pathlib import Path
from typing import Callable
from uuid import uuid4

from fruitfly_agent.lab.improvement.api import (RunPlan, ComponentWorkflow, WorkflowServices,
    GeneratorRegistry, AgentGenerator, AgentComposer, AgentEditor, AgentSelector, AgentReflector,
    FileTaskRunner, WorkspaceTaskSource, component_registry, experience_id,
    SearchActivity, SearchReport, SearchCompletion, TaskMaterial, CaseMeasurements, HoldoutVerification, model_completion, EvidenceInspector)
from fruitfly_agent.interactive.contracts.improvement import (WorkflowConfiguration,
    WorkflowChoice, WorkflowComponentView, ImprovementParameterView, ImprovementPreview)


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
                 tasks=None, publish=None, editor=None, inspector=None, components=None):
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
        self.defaults: Callable[[], dict] = lambda: {}
        self.tasks, self.publish = tasks, publish
        self.previews = {}
        self.services = None
        self.outcome = None
        self._completion = None
        self.running_improver = None

    def registry(self):
        return self.component_factory(tuple(self.targets()))

    def identity(self):
        def identity(value, default):
            return getattr(value, 'implementation_id',
                getattr(value, '__module__', type(value).__module__) + '.' +
                getattr(value, '__qualname__', type(value).__qualname__)) if value is not None else default
        return {'workflow': 'propose-probe-compose-v1',
                'generators': tuple(asdict(d) | {'required_capabilities': sorted(d.required_capabilities)} for d in self.generators.definitions()),
                'stages': {name: identity(value, default) for name, value, default in (
                    ('editor', self.editor_factory, 'workspace-editor-v1'),
                    ('inspector', self.inspector_factory, 'workspace-inspector-v1'),
                    ('compose', self.composer_factory, 'agent-composer-v1'),
                    ('select', self.selector_factory, 'agent-selector-v1'),
                    ('reflect', self.reflector_factory, 'agent-reflector-v1'),
                    ('workflow', self.controller_factory, 'propose-probe-compose-v1'))}}

    def workflow_configuration(self):
        registry = self.registry()
        packages = tuple(self.tasks().summaries()) if self.tasks is not None else ()
        measured = self.measurements is not None or any(not p.error for p in packages)
        runner_caps = getattr(self.runner_factory, 'capabilities', FileTaskRunner.capabilities)
        components = []
        for document in registry.snapshot().components:
            adapter = registry.adapters[document.component_id]
            missing: frozenset[str] = getattr(adapter, 'required_capabilities', frozenset()) - runner_caps
            reason = 'Missing execution capabilities: ' + ', '.join(sorted(missing)) if missing else ''
            if document.role == 'I' and 'improver-comparison' not in runner_caps:
                reason = 'This runner does not compare improver behavior.'
            components.append(WorkflowComponentView(document.component_id,
                getattr(getattr(adapter, 'target', adapter), 'label', document.component_id), document.kind, document.role, not reason, reason))
        generators = []
        for definition in self.generators.definitions():
            missing = definition.required_capabilities - ({'editor', 'model'} | ({'measurements'} if measured else set()))
            generators.append(WorkflowChoice(definition.generator_id, definition.label, not missing,
                                              'Missing capabilities: ' + ', '.join(sorted(missing)) if missing else ''))
        return WorkflowConfiguration(tuple(components), tuple(generators),
            (WorkflowChoice('parallel', 'Parallel exploration'), WorkflowChoice('sequential', 'Sequential refinement')),
            (WorkflowChoice('behavior', 'Execution evidence', detail='Selection is not a proof of correctness.'),
             WorkflowChoice('scored', 'Measured feedback', measured,
                            '' if measured else 'No measurement source is registered.')),
            (WorkflowChoice('task', 'Current task only'),
             WorkflowChoice('persistent', 'Publish a persistent candidate', self.publish is not None,
                            '' if self.publish else 'No candidate publication capability is registered.')),
            tuple(ImprovementParameterView(name, label, kind, self.defaults().get(name, default), minimum, maximum, 'budget', description)
                for name, label, kind, default, minimum, maximum, description in (
                    ('width', 'Exploration width', 'integer', 1, 1, 10, 'Candidates per diagnostic scope in parallel mode.'),
                    ('depth', 'Refinement depth', 'integer', 1, 1, 10, 'Successive rounds in sequential mode.'),
                    ('max_model_calls', 'Model calls', 'integer', 64, 1, 10000, 'One shared allocation for editor and task executions.'),
                    ('max_executions', 'Task executions', 'integer', 32, 1, 1000, 'Includes reference, probes and composed executions.'),
                    ('operation_timeout', 'Operation timeout', 'number', 120, 1, 14400, 'Seconds per stage operation.'))),
            (WorkflowChoice('', 'Current task and input files'), *(WorkflowChoice(s.pack_id, s.name,
                not s.error, s.error, f'{s.train_count} training · {s.validation_count} selection · {s.holdout_count} holdout')
                for s in packages)))

    def preview(self, request, *, material=None):
        options = self.workflow_configuration()
        if not request.instruction.strip() and not request.task_pack_id and material is None:
            raise ValueError('provide the current task instruction')
        if request.verification == 'scored' and not request.task_pack_id and self.measurements is None:
            raise ValueError('measured feedback requires a task package or registered measurement source')
        available = {c.component_id for c in options.components if c.available}
        if not request.component_ids or set(request.component_ids) - available:
            raise ValueError('select available editable components')
        for selected, choices in ((request.generator_id, options.generators), (request.mode, options.modes),
                                  (request.verification, options.verification), (request.scope, options.scopes)):
            if not any(c.choice_id == selected and c.available for c in choices):
                raise ValueError('selected workflow capability is unavailable')
        parent = self.version()
        plan = RunPlan('job-' + uuid4().hex, parent, request.component_ids, request.generator_id,
            request.mode, request.width, request.depth, request.scope, request.verification,
            request.max_model_calls, request.max_executions, request.operation_timeout, request.direction)
        comparison = None
        if material is not None:
            task = material
        elif request.task_pack_id:
            if self.tasks is None:
                raise ValueError('task packages are unavailable')
            suite = self.tasks().freeze(request.task_pack_id, request.component_ids[0])
            holdout = self.tasks().holdout(request.task_pack_id)
            if request.scope == 'persistent' and not holdout:
                raise ValueError('persistent improvement requires independent holdout tasks')
            task = TaskMaterial('training-task', suite.train[0].input, origin='task-pack:' + request.task_pack_id,
                                environment_id='file-workspace-v1')
            selection = tuple(TaskMaterial(f'selection-{i}', c.input, origin=task.origin,
                environment_id=task.environment_id) for i, c in enumerate(suite.validation))
            confirmation = tuple(TaskMaterial(f'holdout-{i}', c.input, origin=task.origin,
                environment_id=task.environment_id) for i, c in enumerate(holdout))
            regression = tuple(TaskMaterial(f'regression-{i}', c.input, origin=task.origin,
                environment_id=task.environment_id) for i, c in enumerate(suite.train))
            comparison = (suite, selection, confirmation, tuple(holdout), regression)
        else:
            task = WorkspaceTaskSource(self.workspace, self.artifacts).freeze('task-' + uuid4().hex,
                request.instruction, paths=request.input_paths, environment_id='file-workspace-v1')
            if request.scope == 'persistent' and self.verifier is None:
                raise ValueError('select a task package with independent verification material')
        registry = self.registry()
        baseline = registry.snapshot()
        experience = self.experience.snapshot()
        token = uuid4().hex
        if len(self.previews) >= 16:
            self.previews.pop(next(iter(self.previews)))
        self.previews[token] = (plan, task, baseline, registry, experience, self.manifest()['digest'], comparison)
        return ImprovementPreview(plan.generator_id, 'Component improvement',
            'Runs model requests and repeated task executions in a detached file workspace. Calls may incur charges. '
            'Current-task selection does not change profile defaults or prove a quality gain.',
            (('Task', task.instruction), ('Input files', ', '.join(r.path for r in task.inputs) or '(none)'),
             ('Components', ', '.join(plan.component_ids)), ('Candidate generator', plan.generator_id),
             ('Exploration', f'{plan.mode}; width={plan.width}; depth={plan.depth}'),
             ('Verification', plan.feedback), ('Effect scope', plan.purpose),
             ('Model calls', str(plan.max_model_calls)), ('Task executions', str(plan.max_executions)),
             ('Execution environment', task.environment_id), ('Experience snapshot', experience_id(experience))),
            target='component-bundle', preview_token=token)

    async def improve(self, manifest, direction, *, preview_token):
        self._completion, self.outcome = None, None
        if preview_token not in self.previews:
            raise ValueError('unknown or consumed component preview')
        plan, task, baseline, registry, experience, digest, comparison = self.previews.pop(preview_token)
        if (manifest['digest'] != digest or self.manifest()['digest'] != digest or self.version() != plan.parent
                or direction != plan.direction or self.registry().snapshot() != baseline
                or experience_id(self.experience.snapshot()) != experience_id(experience)):
            raise ValueError('task improvement conditions changed; preview again')
        root = self.workspace / '.fruitfly/improvement/jobs' / plan.job_id
        if not root.resolve().is_relative_to(self.workspace.resolve()):
            raise ValueError('job records must remain inside the workspace')
        root.mkdir(parents=True, exist_ok=False)
        (root / 'plan.json').write_text(json.dumps({'schema_version': 1, 'plan': asdict(plan),
            'task': asdict(task), 'baseline': baseline.to_dict(), 'experience': experience_id(experience),
            'verification': {'source_hash': comparison[0].source_hash,
                'policy_id': comparison[0].evaluation_policy.policy_id,
                'selection': [t.material_id for t in comparison[1]],
                'holdout': [t.material_id for t in comparison[2]],
                'regression': [t.material_id for t in comparison[4]]} if comparison else None}, ensure_ascii=False), encoding='utf-8')
        stream = (root / 'events.jsonl').open('x', encoding='utf-8')
        def record(event, **fields):
            stream.write(json.dumps({'event': event, **fields}, ensure_ascii=False) + '\n')
            stream.flush()
        services = WorkflowServices(plan, record=record)
        self.services, self.running_improver, self.outcome = services, self, None
        self._completion = None
        stop = 'error'
        try:
            services.completer = model_completion(self.editor_configuration())
            if self.editor_factory is AgentEditor:
                editor = self.editor_factory(self.editor_configuration(), self.artifacts, registry,
                                             instructions=self.editor_instructions())
            else:
                editor = self.editor_factory(self.editor_configuration(), self.artifacts, registry)
            services.own(editor)
            services.editor = editor.edit
            inspector = (self.inspector_factory(self.editor_configuration(), self.artifacts, registry)
                if self.inspector_factory is not None else editor if isinstance(editor, EvidenceInspector)
                else AgentEditor(self.editor_configuration(), self.artifacts, registry,
                                 instructions=self.editor_instructions()))
            services.own(inspector)
            runner = (self.runner_factory(plan, registry, self.artifacts, services) if self.runner_factory else
                      FileTaskRunner(self.config(), registry, self.artifacts, services))
            services.own(runner)
            composer = self.composer_factory(plan, services) if self.composer_factory else AgentComposer()
            services.own(composer)
            selector = self.selector_factory(plan, services) if self.selector_factory else AgentSelector(inspector, services)
            services.own(selector)
            reflector = self.reflector_factory(plan, services) if self.reflector_factory else AgentReflector(inspector, services)
            services.own(reflector)
            measurements, verifier = self.measurements, self.verifier
            if comparison is not None:
                suite, selection, confirmation, holdout, regression = comparison
                if self.tasks().source_hash(suite.pack_id) != suite.source_hash:
                    raise ValueError('verification task package changed after preview')
                cases = {task.task_id: suite.train[0],
                    **{t.task_id: c for t, c in zip(regression, suite.train)},
                    **{t.task_id: c for t, c in zip(selection, suite.validation)},
                    **{t.task_id: c for t, c in zip(confirmation, holdout)}}
                measurements = CaseMeasurements(suite.evaluation_policy, cases)
                async def execute_verification(material, harness):
                    services.reserve('execution')
                    receipt = await services.operation(runner.execute(plan, material, harness))
                    if (receipt.material_id != material.material_id or receipt.harness_id != harness.snapshot_id
                            or receipt.conditions_id != plan.conditions_id or receipt.initial_state_id != plan.parent.state):
                        raise ValueError('verification execution differs from frozen comparison')
                    record('verification-execution', receipt=asdict(receipt))
                    return receipt
                verifier = HoldoutVerification(baseline=baseline, selection=selection, holdout=confirmation,
                    execute=execute_verification, measurements=measurements,
                    direction=suite.direction, regression=regression) if confirmation else None
            workflow = self.controller_factory(generators=self.generators, components=registry,
                runner=runner, composer=composer, selector=selector, reflector=reflector,
                measurements=measurements, verifier=verifier)
            services.own(workflow)
            outcome = await workflow.run(plan, task, baseline, services, experience=experience)
            services.check()
            if self.version() != plan.parent:
                raise ValueError('production H/I/S changed during task improvement')
            self.outcome = outcome
            stop = outcome.stop_reason
            services.record('workflow-completed', stop_reason=stop,
                selected=outcome.selected.run_id if outcome.selected else None,
                assurance=outcome.decision.assurance if outcome.decision else 'unavailable')
            (root / 'result.json').write_text(json.dumps(asdict(outcome), ensure_ascii=False), encoding='utf-8')
            # Experience is a separately recorded S update, committed only at
            # this completed task boundary. Persistent jobs defer it to adoption.
            if outcome.experience and plan.purpose == 'task':
                snapshot = self.experience.commit(outcome.experience, expected_snapshot=experience_id(experience))
                record('experience-committed', before=experience_id(experience), after=snapshot)
            if (plan.purpose == 'persistent' and outcome.decision is not None
                    and outcome.decision.assurance == 'verified'):
                return self.publish(outcome, baseline, tuple(registry.adapters.values()))
            return ()
        finally:
            await services.close()
            self._completion = SearchCompletion(SearchReport(stop_reason=stop,
                model_calls=services.used['model'], model_limit=plan.max_model_calls,
                trial_calls=services.used['execution'], trial_limit=plan.max_executions),
                (('Component job', str(root.relative_to(self.workspace))),
                 ('Assurance', self.outcome.decision.assurance if self.outcome and self.outcome.decision else 'unavailable')),
                summary=('Persistent candidate verification finished; review the result before adoption.'
                         if plan.purpose == 'persistent' else 'Current-task refinement finished; profile defaults are unchanged.'),
                output=self.outcome.selected.output if self.outcome and self.outcome.selected else '',
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

    def progress(self):
        if self.services is None:
            return None
        used, plan = self.services.used, self.services.plan
        phase = self.services.events[-1][0] if self.services.events else 'Preparing task'
        return SearchActivity(phase, model_calls=used['model'], model_limit=plan.max_model_calls,
                              trial_calls=used['execution'], trial_limit=plan.max_executions)

    def cancel(self):
        if self.services is None:
            return False
        self.services.signal.set()
        return True
