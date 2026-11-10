"""Public persistent research service; role factories and task executors are injected."""
import json
from pathlib import Path
from fruitfly_agent.improvement.contracts.activities import ActivitySpec, ActivityResult
from fruitfly_agent.improvement.contracts.research import ResearchRevision, ResearchBatch
from fruitfly_agent.improvement.contracts.tasks import Resource
from fruitfly_agent.improvement.contracts.versions import canonical_json
from fruitfly_agent.improvement.stages.controller import ResearchController
from fruitfly_agent.improvement.stages.services import StageServices
from fruitfly_agent.run.storage.research import ResearchStore




class ResearchService:
    def __init__(self, workspace, research_id, artifacts, *, plan=None, proposal=None, harness=None,
                 organizer=None, assessor=None, executor=None, services_factory=None, role_identity=None, journal=None,
                 external_stages=None):
        self.store = journal or ResearchStore(workspace, research_id)
        self.artifacts, self.plan, self.proposal = artifacts, plan, proposal
        self.harness = harness
        self.organizer, self.assessor, self.executor = organizer, assessor, executor
        self.services_factory = services_factory
        self.role_identity = dict(role_identity or {})
        self.source_id = None
        self.external_stages = dict(external_stages or {})
        self.controller = self.build_controller()

    def build_controller(self):
        from fruitfly_agent.lab.improvement.api import StageContext, builtin_stage_handlers
        context = StageContext(self.plan, self.proposal, self.organizer, self.assessor, self.executor,
            self.put, self.read, self.read_batch, self.input_batch, self.create_services)
        implementations = {('import', 'research-import-v1'): self._import,
            **builtin_stage_handlers(context)}
        for name, implementation in self.external_stages.items():
            implementations[(name, 'research-' + name + '-v1')] = implementation
        return ResearchController(self.store, self.artifacts, implementations)

    def put(self, path, value, kind='diagnostic'):
        return Resource(path, self.artifacts.put(canonical_json(value).encode()), 'application/json', kind)

    def read(self, resource):
        return json.loads(self.artifacts.read(resource.artifact_id))

    def read_batch(self, resource):
        batch = ResearchBatch.from_dict(self.read(resource))
        issues = []
        for references in (*(t.inputs for t in batch.tasks), *(r.artifacts for r in batch.records)):
            for reference in references:
                try:
                    self.artifacts.read(reference.artifact_id)
                except (ValueError, KeyError, OSError) as exc:
                    issue = {'name': 'unavailable_evidence', 'path': reference.path,
                        'artifact_id': reference.artifact_id, 'error': type(exc).__name__}
                    if issue not in batch.observations and issue not in issues:
                        issues.append(issue)
        return ResearchBatch(batch.tasks, batch.records, (*batch.observations, *issues))

    def input_batch(self, resources):
        tasks, records, observations = {}, {}, []
        for resource in resources:
            batch = self.read_batch(resource)
            for task in batch.tasks:
                if task.task_id in tasks and tasks[task.task_id] != task:
                    raise ValueError('conflicting task identity across input batches: ' + task.task_id)
                tasks[task.task_id] = task
            for record in batch.records:
                if record.run_id in records and records[record.run_id] != record:
                    raise ValueError('conflicting execution identity: ' + record.run_id)
                records[record.run_id] = record
            observations.extend(batch.observations)
        return ResearchBatch(tuple(tasks.values()), tuple(records.values()), tuple(observations))

    async def perform_named(self, kind, inputs, *, parameters=None, fresh=False, retry_unresolved=False):
        from fruitfly_agent.improvement.contracts.stages import StageInputs
        if not isinstance(inputs, StageInputs):
            raise TypeError('named stages require StageInputs')
        inputs.validate_for(kind)
        resources = (() if inputs.harness is None else (inputs.harness,)) + inputs.batches + inputs.evidence + inputs.assessments + inputs.context
        return await self.perform(kind, resources, parameters={**(parameters or {}),
            'named_inputs': inputs.to_dict()}, fresh=fresh, retry_unresolved=retry_unresolved)

    def revise(self, configuration, *, direction=''):
        with self.store.owner():
            state = self.controller.state()
            revision = ResearchRevision(configuration, state.revisions[-1]['identity'] if state.revisions else '', direction)
            return self.controller.revise(revision)

    async def perform(self, kind, inputs, *, parameters=None, fresh=False, retry_unresolved=False):
        self.controller = self.build_controller()
        parameters = dict(parameters or {})
        if self.source_id is None:
            from fruitfly_agent.run.storage.snapshots import capture_source_tree
            source = capture_source_tree(Path(__file__).resolve().parents[3])
            self.source_id = self.artifacts.put(canonical_json(source.to_dict()).encode())
        parameters['implementation_source'] = self.source_id
        if self.plan is not None:
            if kind in {'propose', 'execute'}:
                parameters['plan_conditions'] = self.plan.conditions_id
            field = {'organize': 'organizer_seconds', 'assess': 'evaluator_seconds',
                'compare': 'evaluator_seconds', 'propose': 'editor_seconds', 'execute': 'execution_seconds'}.get(kind)
            if field:
                parameters['timeout_seconds'] = getattr(self.plan.timeouts, field)
        if kind in self.role_identity:
            parameters['role_identity'] = self.role_identity[kind]
        spec = ActivitySpec(kind, 'research-' + kind + '-v1', tuple(inputs), parameters)
        with self.store.owner():
            result = await self.controller.perform(spec, fresh=fresh, retry_unresolved=retry_unresolved)
            if kind in {'eval', 'import', 'assess', 'execute'}:
                for resource in result.outputs:
                    if resource.path != 'batch.json':
                        continue
                    self.read_batch(resource)
            elif kind == 'organize':
                # Missing originals remain explicit in coverage and fail only on
                # access; they do not invalidate an already retained readable view.
                self.read(result.outputs[0])
            return result

    def create_services(self):
        if self.plan is None:
            raise ValueError('model/task research requires a current authorized plan')
        services = self.services_factory(self.plan) if self.services_factory else StageServices(self.plan)
        original = services.sink
        def record(event, **fields):
            original(event, **fields)
            resource = self.put('event.json', {'event': event, **fields})
            self.store.append({'type': 'role-event', 'data': {'artifact_id': resource.artifact_id}})
        services.sink = record
        return services

    async def _import(self, spec):
        # Validate the serialized public batch, including its task/receipt grant.
        resources = tuple(resource for resource in spec.inputs if resource.path == 'batch.json')
        if len(resources) != 1:
            raise ValueError('import requires one named batch.json resource')
        batch = self.input_batch(resources)
        from fruitfly_agent.lab.improvement.api import batch_view
        views = batch_view(batch.tasks, batch.records, batch.observations, self.artifacts)
        return ActivityResult((self.put('batch.json', batch.to_dict()),
            *(self.put(name, value) for name, value in views.items())))





