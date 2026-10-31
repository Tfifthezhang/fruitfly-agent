"""Native file material preparation and verification, independent of Run."""
from uuid import uuid4
from dataclasses import asdict

from fruitfly_agent.improvement.contracts.experiments import ExecutionDefinition, ExecutionParameter, MaterialOption, PreparedExecution, ExecutionPorts
from fruitfly_agent.improvement.contracts.tasks import TaskMaterial
from fruitfly_agent.improvement.contracts.versions import canonical_json
from fruitfly_agent.improvement.contracts.versions import content_hash
from ..materials import WorkspaceTaskSource
from ..execution.file_runner import FileTaskRunner
from ..assessment.verification import CaseMeasurements, HoldoutVerification
from ..assessment.online import AssessedRunner
from ..assessment.metrics import ProcessMetrics
from .deliverables import DeliverySpec
from ..verification.delivery import DeliveryValidationRunner, validate_delivery_backend


def delivery_spec(context, task, parameters):
    path = parameters['delivery_manifest']
    if not path:
        return None
    from fruitfly_agent.improvement.contracts.validation import relative_path
    relative_path(path)
    if context.delivery_backend is None:
        raise ValueError('delivery validation requires an explicitly supplied clean execution backend')
    validate_delivery_backend(context.delivery_backend)
    resource = next((r for r in task.inputs if r.path == path), None)
    if resource is None:
        raise ValueError('delivery manifest must be a frozen task input')
    spec = DeliverySpec.parse(context.artifacts.read(resource.artifact_id))
    if set(spec.inputs) - {r.path for r in task.inputs}:
        raise ValueError('delivery inputs must be frozen task inputs')
    return spec


def materials(context):
    packages = context.tasks.summaries() if context.tasks is not None else ()
    return (MaterialOption('', 'Current task and input files'), *(MaterialOption(s.pack_id, s.name,
        f'{s.train_count} training · {s.validation_count} selection · {s.holdout_count} holdout', s.error) for s in packages))


def component_scope(context, material_id, components):
    if not material_id:
        return components
    if context.tasks is None:
        raise ValueError('task packages are unavailable')
    compatible = context.tasks.compatible_targets(material_id)
    return tuple(name for name in components if name in compatible)


def prepare(context, request):
    parameters = definition().normalize(request.parameters)
    if request.feedback == 'scored' and not request.material_id and context.measurements is None:
        raise ValueError('measured feedback requires a task package or registered measurement source')
    if request.material_id:
        if parameters['delivery_manifest']:
            raise ValueError('task-package execution has no file delivery manifest; use a file source')
        if context.tasks is None:
            raise ValueError('task packages are unavailable')
        if set(request.component_ids) - set(context.tasks.compatible_targets(request.material_id)):
            raise ValueError('task package does not support every selected component')
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
        prepared.private = (suite, holdout, parameters)
        return prepared
    if not request.instruction.strip():
        raise ValueError('provide the current task instruction')
    if request.scope == 'persistent' and context.verifier is None:
        raise ValueError('select a task package with independent verification material')
    task = WorkspaceTaskSource(context.workspace, context.artifacts).freeze('task-' + uuid4().hex,
        request.instruction, paths=request.input_paths, environment_id='file-workspace-v1')
    delivery_spec(context, task, parameters)
    return PreparedExecution(task, task.material_id, (), lambda: task.material_id,
                             (None, (), parameters))


def build(context, prepared):
    plan, services = context.plan, context.services
    suite, holdout, parameters = prepared.private
    runner = (context.runner_factory(plan, context.components, context.artifacts, services)
              if context.runner_factory else FileTaskRunner(context.config, context.components, context.artifacts, services,
                  tool_names={tool.name for tool in context.config.tools}))
    services.own(runner)
    if parameters['assessment_interval']:
        runner = AssessedRunner(runner, artifacts=context.artifacts, services=services,
            assessors=(ProcessMetrics,), interval=parameters['assessment_interval'])
    spec = delivery_spec(context, prepared.task, parameters)
    if spec is not None:
        runner = DeliveryValidationRunner(runner, spec, context.delivery_backend, context.artifacts, services)
    measurements, verifier = context.measurements, context.verifier
    if suite is not None:
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
            services.observe('execution')
            receipt = await services.operation(runner.execute(plan, material, harness), stage='execute')
            if (receipt.task_id != material.task_id or receipt.material_id != material.material_id
                    or receipt.harness_id != harness.snapshot_id or receipt.conditions_id != plan.conditions_id
                    or receipt.initial_state_id != plan.parent.state):
                raise ValueError('verification execution differs from frozen comparison')
            services.record('verification-execution', receipt=asdict(receipt))
            return receipt
        async def evaluate(material, receipt):
            return await services.operation(measurements.measure(material, receipt), stage='evaluator')
        verifier = HoldoutVerification(baseline=context.components.snapshot(), selection=selection, holdout=confirmation,
            execute=execute, measurements=measurements, direction=suite.direction, regression=regression,
            artifacts=context.artifacts, evaluate=evaluate) if confirmation else None
    return ExecutionPorts(runner, measurements, verifier)


def definition():
    return ExecutionDefinition('file-task', 'Agent task execution', 'file-task-v3', frozenset({'H', 'S'}),
        FileTaskRunner.capabilities, materials, prepare, build,
        parameters=(ExecutionParameter('delivery_manifest', 'Delivery manifest input', 'string', '', description='Frozen JSON input declaring the output entrypoint, dependencies and permitted inputs; requires an injected backend.'),
            ExecutionParameter('assessment_interval', 'Online assessment interval', 'integer', 0, 0, 1000,
            'Events per assessment; 0 disables online process/resource assessment.')), accepts_runner_override=True,
        component_scope=component_scope)
