"""Prepare an external task stream and reuse the public component workflow."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from uuid import uuid4

from fruitfly_agent.lab.improvement.api import (TaskMaterial, Resource, ExecutionRecord, Measurement,
    TaskReference, TaskRunEvidence, SearchReport, SearchCompletion, bundle_text)
from fruitfly_agent.lab.algorithms.targets import canonical_json, content_hash
from fruitfly_agent.interactive.contracts.improvement import WorkflowRequest, ImprovementPreview
from .pipeline import RunComponentJobs


class RuntimeTrialRunner:
    """Validate attributable official receipts; grader feedback stays outside editing."""
    def __init__(self, *, executor, tasks, versions, target, artifacts, manifest, services,
                 calls_per_trial=24, timeout=1800):
        self.executor, self.tasks, self.versions = executor, tasks, versions
        self.target, self.artifacts, self.manifest, self.services = target, artifacts, manifest, services
        self.calls_per_trial, self.timeout = calls_per_trial, timeout
        self.capabilities = frozenset('tool:' + name for name in manifest.get('tools', ()))
        self.environments, self.scores = {}, {}

    async def execute(self, plan, task, harness):
        call_allocation = min(self.calls_per_trial, plan.max_model_calls - self.services.used['model'])
        if call_allocation < 1:
            self.services.reserve('model')
        original = self.tasks[task.material_id]
        text = bundle_text(self.target, harness)
        snapshot = self.target.snapshot()
        candidate = self.versions.text_candidate(plan.parent, snapshot, text) if text != snapshot.text else None
        version = candidate.version if candidate else plan.parent
        fixed = {a['id']: self.versions.artifacts.read_text(a['id']) for a in self.manifest.get('data_artifacts', ())}
        prompt = self.manifest['base_prompt'].get('reference', '')
        if prompt.startswith('sha256:'):
            fixed[prompt] = self.versions.artifacts.read_text(prompt)
        lease = uuid4().hex
        payload = {'schema_version': 1, 'lease_id': lease, 'version': version.to_dict(),
            'harness': json.loads(self.versions.artifacts.read_text(version.harness)),
            'state': self.versions.snapshots.read(version.state).to_dict(),
            'target': {'role': snapshot.role, 'schema': snapshot.schema, 'kind': snapshot.binding.kind,
                       'key': snapshot.binding.key, 'snapshot': snapshot.to_dict()},
            'text': text, 'conditions_id': plan.conditions_id, 'allow_local_operations': True,
            'expected_models': self.manifest['models'], 'artifacts': fixed,
            'max_model_calls': call_allocation, 'max_output_tokens': 4096,
            'instruction': original.instruction}
        self.services.reserve('model', call_allocation)
        self.services.record('external-lease', lease_id=lease, reserved=call_allocation, task_id=task.task_id)
        result = await self.executor.run(original, payload, timeout=self.timeout, signal=self.services.signal)
        evidence = TaskRunEvidence.from_dict(result['evidence'])
        receipt = self.executor.runtime_receipt(result)
        if (evidence.task != original or evidence.version != version or evidence.conditions_id != plan.conditions_id
                or evidence.model_calls is None or evidence.model_calls > call_allocation
                or not evidence.runtime_digest or not receipt.get('instruction_hash')
                or receipt.get('lease_id') != lease or receipt.get('version') != version.to_dict()
                or receipt.get('conditions_id') != plan.conditions_id or receipt.get('model_calls') != evidence.model_calls
                or (receipt.get('runtime') or {}).get('digest') != evidence.runtime_digest
                or (receipt.get('runtime') or {}).get('models') != self.manifest['models']
                or content_hash(canonical_json(receipt.get('execution_environment'))) != evidence.environment_digest):
            raise ValueError('external execution receipt differs from its authorized invocation')
        previous = self.environments.setdefault(task.material_id, (evidence.environment_digest, receipt.get('instruction_hash')))
        if previous != (evidence.environment_digest, receipt.get('instruction_hash')):
            raise ValueError('task environment or effective instruction changed across probes')
        self.services.used['model'] -= call_allocation - evidence.model_calls
        run_id = 'external-' + lease
        resources = []
        for artifact in evidence.artifacts:
            if artifact.kind not in {'trajectory', 'deliverable'}:
                continue
            content = self.executor.read_evidence(result, artifact)
            resources.append(Resource(artifact.path, self.artifacts.put(content.encode('utf-8')),
                                      'text/plain; charset=utf-8', artifact.kind))
        record = ExecutionRecord(run_id, task.task_id, task.material_id, harness.snapshot_id, plan.parent.state,
            plan.conditions_id, 'completed' if evidence.status in {'scored', 'unscored'} else 'error',
            evidence.output, tuple(resources), evidence.model_calls)
        if evidence.score is not None:
            self.scores[run_id] = Measurement(run_id, 'official-task-reward-v1', evidence.score, evidence.feedback)
        return record


class RunExternalJobs:
    """Benchmark preparation is an external source adapter, not a search algorithm."""
    def __init__(self, *, jobs, versions, manifest, targets, workspace, freeze_runtime,
                 config, artifacts, experience, bindings, publish):
        self.jobs, self.versions, self.manifest, self.targets = jobs, versions, manifest, targets
        self.workspace, self.freeze_runtime, self.config = Path(workspace), freeze_runtime, config
        self.artifacts, self.experience, self.bindings, self.publish = artifacts, experience, bindings, publish
        self.previews = {}
        self.running_improver = None
        self._completion = None

    def preview_selection(self, selection, executor, direction=''):
        selection = dict(selection)
        count = selection.get('task_limit', 1)
        if type(count) is not int or not 1 <= count <= 12:
            raise ValueError('external task streams require 1–12 tasks')
        component_ids = tuple(selection.get('component_ids') or ('base_prompt',))
        request = WorkflowRequest(instruction='External task stream', component_ids=component_ids,
            generator_id=selection.get('generator_id') or 'agent-editor-v1',
            mode=selection.get('mode', 'parallel'), width=selection.get('width', 1), depth=selection.get('depth', 1),
            max_model_calls=selection.get('max_model_calls', 128), max_executions=selection.get('max_executions', 64),
            operation_timeout=selection.get('operation_timeout', 1800), direction=direction)
        # Validate typed allocations offline; external preparation still starts
        # only after Application owns the explicitly submitted job.
        from fruitfly_agent.lab.improvement.api import RunPlan
        parent = self.versions.freeze()
        RunPlan('external-preview', parent, component_ids, request.generator_id, selection.get('mode', 'parallel'),
                request.width, request.depth, max_model_calls=request.max_model_calls,
                max_executions=request.max_executions, operation_timeout=request.operation_timeout)
        registry = self.jobs.registry()
        definition = next((d for d in self.jobs.generators.definitions() if d.generator_id == request.generator_id), None)
        if definition is None or definition.required_capabilities - {'editor', 'model'}:
            raise ValueError('external generation requires an available behavior-based generator')
        capabilities = frozenset('tool:' + t.name for t in self.config().tools)
        for name in component_ids:
            document = registry.snapshot().component(name)
            if document.role == 'I' or getattr(registry.adapters[name], 'required_capabilities', frozenset()) - capabilities:
                raise ValueError('external runner cannot execute the selected component')
        token = uuid4().hex
        self.previews[token] = (selection, executor, request, parent, self.manifest()['digest'])
        return ImprovementPreview(request.generator_id, 'External task component improvement',
            'Downloads task materials and images and runs model/container services. Calls may incur charges. '
            'Refinement uses execution evidence; benchmark grading is not supplied to the editor.',
            (('Source', selection['benchmark_id']), ('Task count', str(count)),
             ('Components', ', '.join(component_ids)), ('Exploration', request.mode),
             ('Model calls across the stream', str(request.max_model_calls)),
             ('Task executions across the stream', str(request.max_executions)),
             ('Effect scope', 'Current tasks; no profile defaults are changed')),
            target='component-bundle', preview_token=token)

    async def improve(self, manifest, direction, *, preview_token):
        self._completion = None
        if preview_token not in self.previews:
            raise ValueError('unknown or consumed external preview')
        selection, executor, request, parent, digest = self.previews.pop(preview_token)
        if (self.manifest()['digest'] != digest or manifest['digest'] != digest
                or self.versions.freeze() != parent or direction != request.direction):
            raise ValueError('external task conditions changed; preview again')
        bundle = await executor.prepare_tasks(selection)
        tasks = tuple(TaskReference.from_dict(t) for t in bundle['tasks'])
        if len(tasks) != selection['task_limit'] or bundle['benchmark_id'] != selection['benchmark_id']:
            raise ValueError('prepared external tasks differ from the authorized selection')
        root = self.workspace / '.fruitfly/improvement/external' / uuid4().hex
        root.mkdir(parents=True)
        runtime = self.freeze_runtime(root)
        runtime_hashes = {str(path): content_hash(path.read_text(encoding='utf-8'))
            for path in (root / 'runtime/config.yaml', root / 'runtime/models.yaml')}
        harness = json.loads(self.versions.artifacts.read_text(parent.harness))
        source = self.versions.snapshots.materialize(harness['source'], root / 'source')
        material_root = executor.owned_path(bundle['material_root'])
        materials = {key: executor.owned_path(material_root / path) for key, path in bundle['materials'].items()}
        executor.configure(runtime=runtime, benchmark_id=bundle['benchmark_id'], materials=materials,
                           source_root=source, runtime_hashes=runtime_hashes)
        remaining_calls, remaining_runs = request.max_model_calls, request.max_executions
        outputs, totals = [], [0, 0]
        try:
            for original in tasks:
                if remaining_calls < 1 or remaining_runs < 1:
                    break
                current = self.versions.freeze()
                if (current.harness, current.improver) != (parent.harness, parent.improver):
                    raise ValueError('the common H/I baseline changed during the external task stream')
                material = TaskMaterial('task-' + original.reference_id[-20:], original.instruction,
                    environment_id=original.environment_id, origin=original.dataset)
                target = self.targets()['component-bundle']
                frozen_manifest = {**self.manifest(), 'tools': tuple(t.name for t in self.config().tools)}
                def runner_factory(plan, components, artifacts, services):
                    return RuntimeTrialRunner(executor=executor, tasks={material.material_id: original},
                        versions=self.versions, target=target, artifacts=artifacts,
                        manifest=frozen_manifest, services=services)
                setattr(runner_factory, 'capabilities', frozenset('tool:' + name for name in frozen_manifest['tools']))
                from dataclasses import fields
                values = {f.name: getattr(self.bindings, f.name) for f in fields(self.bindings)
                          if f.name not in {'runner', 'measurements', 'verifier'}}
                jobs = RunComponentJobs(workspace=self.workspace, artifacts=self.artifacts,
                    experience=self.experience, manifest=self.manifest, version=self.versions.freeze,
                    config=self.config, targets=lambda: tuple(self.targets().values()), runner=runner_factory,
                    publish=self.publish, **values)
                jobs.editor_configuration = self.jobs.editor_configuration
                jobs.editor_instructions = self.jobs.editor_instructions
                preview = jobs.preview(replace(request, instruction=original.instruction,
                    max_model_calls=remaining_calls, max_executions=remaining_runs), material=material)
                self.running_improver = jobs
                try:
                    await jobs.improve(self.manifest(), direction, preview_token=preview.preview_token)
                finally:
                    completion = jobs.completion()
                    if completion is not None:
                        totals[0] += completion.report.model_calls
                        totals[1] += completion.report.trial_calls
                report = jobs.completion().report
                remaining_calls -= report.model_calls
                remaining_runs -= report.trial_calls
                if jobs.outcome and jobs.outcome.selected:
                    outputs.append(original.task_id + '\n' + jobs.outcome.selected.output)
                if jobs.outcome and jobs.outcome.stop_reason == 'budget_exhausted':
                    break
            return ()
        finally:
            self._completion = SearchCompletion(SearchReport(stop_reason='completed' if len(outputs) == len(tasks) else 'incomplete',
                model_calls=totals[0], model_limit=request.max_model_calls,
                trial_calls=totals[1], trial_limit=request.max_executions),
                (('External task source', bundle['benchmark_id']),),
                summary=f'Completed {len(outputs)} of {len(tasks)} external tasks; profile defaults are unchanged.',
                output='\n\n'.join(outputs), assurance='selected')
            self.running_improver = None

    def completion(self):
        return self._completion
