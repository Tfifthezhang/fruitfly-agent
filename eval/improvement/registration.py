"""Optional benchmark execution registration; discovery starts no containers/models."""
from dataclasses import dataclass, asdict
import hashlib
from pathlib import Path

from fruitfly_agent.lab.improvement.api import (ExecutionDefinition, MaterialOption,
    PreparedExecution, ExecutionPorts, TaskMaterial, content_hash)
from fruitfly_agent.improvement.contracts.versions import canonical_json
from eval.catalog import builtin_catalog
from eval.contracts import EvaluationRequest
from eval.harbor.host import HostConfig
from eval.harbor.preparation import load_preparation
from .assessment import OfficialMeasurements
from .runner import EvalTaskRunner
from .building import RuntimeConfigBuilder, validate_prepared_runtime


@dataclass(frozen=True)
class BenchmarkMaterial:
    request: object
    host_path: Path
    model_calls: int
    task: TaskMaterial
    source_id: str
    current_source: object


def benchmark_execution(request_path, host_path, *, model_calls=80, execution_id='benchmark-task', executor=None, runtime_override=None):
    """Register one prepared task. Global budget and runtime stay host-owned.

    A model allowance must already be present in the prepared host Agent env.
    Fresh source preparation is required; the old runtime is never silently used.
    """
    if type(model_calls) is not int or model_calls < 1:
        raise ValueError('declare a positive per-execution model allowance')
    request_path, host_path = Path(request_path).resolve(), Path(host_path).resolve()

    def freeze(context):
        request = EvaluationRequest.read(request_path)
        if runtime_override is not None:
            from dataclasses import replace
            request = replace(request, runtime=runtime_override)
        if Path(request.runtime.working_directory).resolve() != Path(context.workspace).resolve():
            raise ValueError('benchmark and improvement workspaces must match')
        if request.execution.attempts != 1 or request.execution.concurrency != 1:
            raise ValueError('register one benchmark task and one attempt per execution')
        descriptor = builtin_catalog().get(request.benchmark.benchmark_id).descriptor
        host = HostConfig.read(Path(context.workspace), host_path)
        if host.agent_env.get('FRUITFLY_MAX_MODEL_CALLS') != str(model_calls):
            raise ValueError('prepare the host with matching FRUITFLY_MAX_MODEL_CALLS before improvement')
        receipt = load_preparation(host, descriptor, request.benchmark.variant)
        if len(receipt['tasks']) != 1:
            raise ValueError('benchmark execution definition currently requires one prepared task')
        # A frozen runtime must support both configured limits and facts. It
        # cannot silently accept a host configuration it does not implement.
        validate_prepared_runtime(receipt)
        task_row = receipt['tasks'][0]
        instruction = (Path(task_row['path']) / 'instruction.md').read_text()
        builder = RuntimeConfigBuilder(context.workspace, request.runtime, context.components)
        identity = content_hash(canonical_json({'request': request.to_dict(), 'request_source': hashlib.sha256(request_path.read_bytes()).hexdigest(), 'host': host_path.read_text(),
            'preparation': receipt['id'], 'model_calls': model_calls,
            'config': hashlib.sha256(builder.source_bytes).hexdigest(),
            'models': hashlib.sha256(builder.model_bytes).hexdigest()}))
        task = TaskMaterial('benchmark-' + identity[7:23], instruction,
            environment_id=receipt['id'], origin='benchmark:' + identity[7:])
        return request, identity, task

    def materials(context):
        try:
            request, identity, task = freeze(context)
            return (MaterialOption(execution_id, request.benchmark.benchmark_id + ' / ' + request.benchmark.variant,
                'Prepared benchmark task; executions call models and containers.'),)
        except (OSError, ValueError, KeyError) as exc:
            return (MaterialOption(execution_id, 'Prepared benchmark task', error=str(exc)),)

    def prepare(context, request):
        if any(context.components.snapshot().component(c).role == 'I' for c in request.component_ids):
            raise ValueError('I changes require a downstream improver comparison execution')
        if request.material_id != execution_id or request.input_paths or request.instruction.strip():
            raise ValueError('select the registered benchmark material without overriding its inputs')
        if request.scope == 'persistent' and context.verifier is None:
            raise ValueError('persistent benchmark adoption requires a separately injected independent verifier')
        evaluation, identity, task = freeze(context)
        context.components.export(context.components.snapshot(), changed_only=False)
        query = lambda: freeze(context)[1]
        material = BenchmarkMaterial(evaluation, host_path, model_calls, task, identity, query)
        return PreparedExecution(task, identity, (('Backend', 'Eval'), ('Per-execution model allowance', str(model_calls))),
            query, material, minimum_budget={'model': model_calls + 8, 'execution': 1})

    def build(context, prepared):
        measurements = OfficialMeasurements()
        runner = context.services.own(EvalTaskRunner(context, prepared.private, measurements, executor=executor))
        return ExecutionPorts(runner, measurements, context.verifier, retain_experience=False)

    return ExecutionDefinition(execution_id, 'Prepared benchmark execution', 'benchmark-improvement-v1',
        frozenset({'H', 'S'}), EvalTaskRunner.capabilities, materials, prepare, build,
        notice='Runs prepared task environments and models. Official rewards are development evidence, not independent assurance.',
        defaults=(('verification', 'scored'), ('scope', 'task'), ('max_model_calls', 512), ('operation_timeout', 1800)),
        uses_configured_tools=True)
