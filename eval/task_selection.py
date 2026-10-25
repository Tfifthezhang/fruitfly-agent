"""Exact subsets of an already validated preparation, never rewritten task data."""
from copy import deepcopy
from pathlib import Path
from typing import Any

from .contracts import EvaluationRequest
from .catalog import builtin_catalog
from .harbor.host import HostConfig
from .harbor.preparation import load_preparation


def select_prepared_tasks(preparation: dict[str, Any], names: tuple[str, ...]) -> dict[str, Any]:
    """The caller validates the original receipt before selecting these rows."""
    tasks = preparation['tasks']
    if not names:
        return preparation
    if len(set(names)) != len(names):
        raise ValueError('duplicate exact task names')
    indexed = {task['id']: task for task in tasks}
    if len(indexed) != len(tasks) or set(names) - set(indexed):
        raise ValueError('requested tasks are outside the frozen prepared selection')
    result = deepcopy(preparation)
    result['tasks'] = [deepcopy(indexed[name]) for name in names]
    result['parent_preparation_id'] = preparation['id']
    result['execution_task_names'] = list(names)
    return result


def list_prepared_tasks(request: EvaluationRequest, *, host_config_path=None) -> dict[str, Any]:
    host = HostConfig.read(Path(request.runtime.working_directory), host_config_path)
    descriptor = builtin_catalog().get(request.benchmark.benchmark_id).descriptor
    preparation = load_preparation(host, descriptor, request.benchmark.variant)
    selected = select_prepared_tasks(preparation, request.benchmark.task_names)
    return {'preparation_id': preparation['id'], 'dataset': descriptor.dataset, 'tasks': selected['tasks']}
