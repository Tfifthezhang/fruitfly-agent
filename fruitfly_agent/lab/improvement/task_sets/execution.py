"""Registered task-set preparation, separate from source and search algorithms."""
from fruitfly_agent.improvement.contracts.task_sets import TaskSetSnapshot
from fruitfly_agent.improvement.contracts.experiments import ExecutionDefinition, MaterialOption, PreparedExecution, ExecutionPorts
from ..workflow.task_sets import TaskSetProblem
from .sampling import sample_batch
from fruitfly_agent.improvement.contracts.plans import TaskSetRunPlan
from fruitfly_agent.improvement.contracts.versions import content_hash, canonical_json
from dataclasses import asdict, replace


def minimum_budget(snapshot, settings):
    """Fund paired initial probes, paired final selection and editor allowance."""
    batch = sample_batch(snapshot, settings.sampling, 0, attempts=settings.execution.attempts)
    entries = {e.key: e for e in snapshot.entries}
    tasks = (*snapshot.selection_entries(), *(entries[key] for key in batch.task_keys))
    return {'model': 2 * sum(e.model_limit for e in tasks) * batch.attempts + 8,
            'execution': 2 * sum(e.execution_limit for e in tasks) * batch.attempts}


def execution_definition(freeze, settings, *, expected, capabilities, roles=frozenset({'H', 'S'})):
    conditions = content_hash(canonical_json({'task_set_id': expected.snapshot_id, 'settings': asdict(settings)}))
    def plan_factory(*args, **kwargs):
        return replace(TaskSetRunPlan(*args, **kwargs), task_set_conditions=conditions)

    def materials(context):
        return (MaterialOption('task-set', 'Frozen task set', 'Shared candidates and joint development evaluation.'),)

    def prepare(context, request):
        if context.generator_definitions and not any(d.generator_id == context.plan.generator_id and d.supports_task_sets
                for d in context.generator_definitions):
            raise ValueError('generator does not declare task-set evidence support')
        if request.scope != 'task' or request.feedback != 'scored':
            raise ValueError('task-set search needs scored development scope; independent adoption is not installed')
        if request.material_id != 'task-set' or request.input_paths or request.instruction:
            raise ValueError('select the registered task set without overriding its material')
        context.component_ids = request.component_ids
        bindings = freeze(context)
        snapshot = TaskSetSnapshot(tuple(e for b in bindings for e in b.entries))
        if snapshot.snapshot_id != expected.snapshot_id:
            raise ValueError('task set changed after experiment checking')
        for name in request.component_ids:
            adapter = context.components.adapters[name]
            document = context.components.snapshot().component(name)
            required: frozenset[str] = getattr(adapter, 'required_capabilities', frozenset())
            if any(document.role not in b.roles or required - b.capabilities for b in bindings):
                raise ValueError('component is unsupported by a selected collection: ' + name)
        def current():
            if any(b.current_source() != b.source_id for b in bindings):
                raise ValueError('task collection changed after preview')
            return snapshot.snapshot_id
        return PreparedExecution(snapshot, snapshot.snapshot_id,
            (('Task count', str(len(snapshot.entries))), ('Development tasks', str(len(snapshot.partition('development')))),
             ('Execution concurrency', str(settings.execution.concurrency)), ('Candidate concurrency', '1'),
             ('Joint aggregation', settings.evaluation.aggregation)), current, bindings,
            minimum_budget=minimum_budget(snapshot, settings))

    def build(context, prepared):
        return ExecutionPorts(None, retain_experience=False,
            search_problem=TaskSetProblem(context, prepared.task, prepared.private, settings))

    return ExecutionDefinition('task-set', 'Joint task-set execution', 'task-set-execution-v1-' + conditions[7:23], roles,
        capabilities, materials, prepare, build,
        notice='Runs shared candidate versions on frozen task collections; scores are development evidence.',
        plan_factory=plan_factory)
