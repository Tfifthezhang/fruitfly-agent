"""Native file material preparation and verification, independent of Run."""
from uuid import uuid4
from dataclasses import asdict

from ..contracts.experiments import ExecutionDefinition, MaterialOption, PreparedExecution, ExecutionPorts
from ..contracts.pipeline import TaskMaterial, canonical_json
from ..contracts.versions import content_hash
from ..materials import WorkspaceTaskSource
from ..workflow.execution import FileTaskRunner
from ..verification import CaseMeasurements, HoldoutVerification


def materials(context):
    packages = context.tasks.summaries() if context.tasks is not None else ()
    return (MaterialOption('', 'Current task and input files'), *(MaterialOption(s.pack_id, s.name,
        f'{s.train_count} training · {s.validation_count} selection · {s.holdout_count} holdout', s.error) for s in packages))


def prepare(context, request):
    if request.feedback == 'scored' and not request.material_id and context.measurements is None:
        raise ValueError('measured feedback requires a task package or registered measurement source')
    if request.material_id:
        if context.tasks is None:
            raise ValueError('task packages are unavailable')
        suite = context.tasks.freeze(request.material_id, request.component_ids[0])
        holdout = context.tasks.holdout(request.material_id)
        if request.scope == 'persistent' and not holdout:
            raise ValueError('persistent improvement requires independent holdout tasks')
        task = TaskMaterial('training-task', suite.train[0].input, origin='task-pack:' + request.material_id,
                            environment_id='file-workspace-v1')
        def current_source():
            identity = context.tasks.source_hash(suite.pack_id)
            if identity != suite.source_hash:
                raise ValueError('verification task package changed after preview')
            return identity
        prepared = PreparedExecution(task, suite.source_hash,
            (('Task package', suite.name), ('Policy', suite.policy_id)),
            current_source, (suite, holdout))
        if request.scope == 'persistent':
            count = 2 * (len(suite.train) + len(suite.validation) + len(holdout))
            prepared.minimum_budget = {'model': count + 1, 'execution': count + 1}
        return prepared
    if not request.instruction.strip():
        raise ValueError('provide the current task instruction')
    if request.scope == 'persistent' and context.verifier is None:
        raise ValueError('select a task package with independent verification material')
    task = WorkspaceTaskSource(context.workspace, context.artifacts).freeze('task-' + uuid4().hex,
        request.instruction, paths=request.input_paths, environment_id='file-workspace-v1')
    return PreparedExecution(task, task.material_id, (), lambda: task.material_id)


def build(context, prepared):
    plan, services = context.plan, context.services
    runner = (context.runner_factory(plan, context.components, context.artifacts, services)
              if context.runner_factory else FileTaskRunner(context.config, context.components, context.artifacts, services))
    services.own(runner)
    measurements, verifier = context.measurements, context.verifier
    reserve = {'model': 0, 'execution': 0}
    if prepared.private is not None:
        suite, holdout = prepared.private
        def project(prefix, cases):
            return tuple(TaskMaterial(f'{prefix}-{i}', c.input, origin=prepared.task.origin,
                environment_id=prepared.task.environment_id) for i, c in enumerate(cases))
        regression, selection, confirmation = (project(p, cases) for p, cases in
            (('regression', suite.train), ('selection', suite.validation), ('holdout', holdout)))
        cases = {prepared.task.task_id: suite.train[0], **{t.task_id: c for ts, cs in
            ((regression, suite.train), (selection, suite.validation), (confirmation, holdout)) for t, c in zip(ts, cs)}}
        measurements = CaseMeasurements(suite.evaluation_policy, cases)
        measurements.direction = suite.direction
        async def execute(material, harness):
            services.reserve('execution')
            receipt = await services.operation(runner.execute(plan, material, harness))
            if (receipt.task_id != material.task_id or receipt.material_id != material.material_id
                    or receipt.harness_id != harness.snapshot_id or receipt.conditions_id != plan.conditions_id
                    or receipt.initial_state_id != plan.parent.state):
                raise ValueError('verification execution differs from frozen comparison')
            services.record('verification-execution', receipt=asdict(receipt))
            return receipt
        verifier = HoldoutVerification(baseline=context.components.snapshot(), selection=selection, holdout=confirmation,
            execute=execute, measurements=measurements, direction=suite.direction, regression=regression,
            artifacts=context.artifacts) if confirmation else None
        if plan.purpose == 'persistent':
            count = 2 * (len(regression) + len(selection) + len(confirmation))
            reserve = {'model': count, 'execution': count}
    return ExecutionPorts(runner, measurements, verifier, verification_reserve=reserve)


def definition():
    return ExecutionDefinition('file-task', 'Agent task execution', 'file-task-v2', frozenset({'H', 'S'}),
        FileTaskRunner.capabilities, materials, prepare, build, accepts_runner_override=True)
