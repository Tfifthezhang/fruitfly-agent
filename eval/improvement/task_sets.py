"""Frozen benchmark collections expose ordinary task runners to joint search."""
from dataclasses import replace
from pathlib import Path
import hashlib
import yaml

from fruitfly_agent.lab.improvement.api import (TaskSetSourceDefinition, TaskEntry, TaskMaterial,
    ScoreSpec, CollectionBinding, ExecutionPorts, content_hash)
from fruitfly_agent.lab.improvement.contracts.versions import canonical_json
from eval.contracts import EvaluationRequest
from eval.catalog import builtin_catalog
from eval.harbor.host import HostConfig
from eval.harbor.preparation import load_preparation
from eval.task_selection import select_prepared_tasks
from .registration import BenchmarkMaterial
from .building import RuntimeConfigBuilder, validate_prepared_runtime
from .assessment import OfficialMeasurements
from .runner import EvalTaskRunner


def freeze(spec, context, *, executor=None):
    allowed = {'id', 'source', 'request', 'host', 'model_calls', 'objective', 'task_names', 'partitions', 'groups'}
    if set(spec) - allowed or 'request' not in spec or 'host' not in spec:
        raise ValueError('benchmark collections need request/host and supported task selection fields')
    request_path, host_path = Path(spec['request']), Path(spec['host'])
    request = EvaluationRequest.read(request_path)
    workspace = Path(context.workspace).resolve()
    declared = Path(request.runtime.working_directory)
    declared = (declared if declared.is_absolute() else workspace / declared).resolve()
    if declared != workspace:
        raise ValueError('benchmark collections must use the experiment workspace')
    request = replace(request, runtime=replace(request.runtime, working_directory=str(workspace)))
    if request.execution.attempts != 1 or request.execution.concurrency != 1:
        raise ValueError('leaf benchmark requests need attempts=1 and concurrency=1; the shared scheduler owns parallelism')
    from fruitfly_agent.runtime_spec import runtime_reference
    config_path, profile_id = runtime_reference(context.workspace, request.runtime.config_path, request.runtime.profile,
        inherited_path=context.runtime_config, inherited_profile=context.runtime_profile)
    request = replace(request, runtime=replace(request.runtime, config_path=str(config_path), profile=profile_id))
    builder = RuntimeConfigBuilder(context.workspace, request.runtime, None)
    if context.runtime_profile and context.runtime_profile != builder.profile:
        raise ValueError('benchmark and task-set runtime profiles differ')
    adapter = builtin_catalog().get(request.benchmark.benchmark_id)
    descriptor = adapter.descriptor
    host = HostConfig.read(Path(context.workspace), host_path)
    limit = spec.get('model_calls', 80)
    if type(limit) is not int or limit < 1 or host.agent_env.get('FRUITFLY_MAX_MODEL_CALLS') != str(limit):
        raise ValueError('prepared benchmark host needs the declared per-task model allowance')
    names = spec.get('task_names', [])
    if not isinstance(names, list) or any(not isinstance(v, str) for v in names):
        raise ValueError('collection task_names must be a list of exact prepared names')
    partitions, groups = spec.get('partitions', {}), spec.get('groups', {})
    if not isinstance(partitions, dict) or not isinstance(groups, dict):
        raise ValueError('partitions and groups must be task-name mappings')
    objective_data = spec.get('objective', {})
    if not isinstance(objective_data, dict) or set(objective_data) - {'minimum', 'maximum', 'direction'}:
        raise ValueError('unsupported benchmark objective fields')
    objective = ScoreSpec(OfficialMeasurements.policy_id, **objective_data)

    def current():
        prepared = load_preparation(host, descriptor, request.benchmark.variant)
        validate_prepared_runtime(prepared)
        selected = select_prepared_tasks(prepared, request.benchmark.task_names)
        selected = select_prepared_tasks(selected, tuple(names))
        return prepared, selected, content_hash(canonical_json({'request': request_path.read_text(),
            'host': host_path.read_text(), 'preparation': prepared['id'], 'tasks': [t['id'] for t in selected['tasks']],
            'config': hashlib.sha256(builder.source.read_bytes()).hexdigest(),
            'models': hashlib.sha256(builder.original_catalog.read_bytes()).hexdigest(),
            'limit': limit, 'objective': objective_data, 'partitions': partitions, 'groups': groups}))

    prepared, selected, identity = current()
    from fruitfly_agent.lab.catalog import load_system_config as load_harness_config
    from fruitfly_agent.lab.catalog import resolve_harness, builtin_catalog as runtime_catalog
    inventory = resolve_harness(load_harness_config(builder.source).select(builder.profile), runtime_catalog())
    capabilities = EvalTaskRunner.capabilities | frozenset('tool:' + name for name in inventory.tools)
    if (set(partitions) | set(groups)) - {t['id'] for t in selected['tasks']}:
        raise ValueError('task metadata cites tasks outside the selected preparation')
    entries, originals = [], {}
    for row in selected['tasks']:
        origin = descriptor.dataset + ':' + row['id']
        key = spec['id'] + '-' + content_hash(origin)[7:31]
        task = TaskMaterial(key, (Path(row['path']) / 'instruction.md').read_text(),
            environment_id=prepared['id'], origin='benchmark:' + content_hash(origin)[7:])
        entries.append(TaskEntry(key, spec['id'], identity, spec['id'], task, objective, origin,
            group_id=groups.get(row['id'], origin), partition=partitions.get(row['id'], 'development'), model_limit=limit))
        originals[key] = row['id']

    def build(leaf):
        measurements = OfficialMeasurements()
        class Runner:
            capabilities = EvalTaskRunner.capabilities
            async def execute(self, plan, task, harness):
                if task.task_id not in originals:
                    raise ValueError('task is outside the prepared collection')
                evaluation = replace(request, benchmark=replace(request.benchmark, task_names=(originals[task.task_id],)))
                material = BenchmarkMaterial(evaluation, host_path, limit, task, identity, lambda: current()[2])
                runner = leaf.services.own(EvalTaskRunner(leaf, material, measurements, executor=executor))
                return await runner.execute(plan, task, harness)
        return ExecutionPorts(Runner(), measurements, retain_experience=False)

    return CollectionBinding(tuple(entries), build, lambda: current()[2], identity, capabilities)


def definition():
    return TaskSetSourceDefinition('eval', 'prepared-eval-collection-v1', freeze)
