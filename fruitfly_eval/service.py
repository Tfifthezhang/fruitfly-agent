"""Reusable Eval operations; argument parsing and presentation belong to callers."""
import json
import os
from pathlib import Path

from .catalog import builtin_catalog
from .contracts import EvaluationRequest


def prepare_evaluation(request, *, host_config_path=None, tasks_only=False, progress=None, catalog=None):
    from .installation import resolve_installation
    from .harbor.preparation import prepare
    adapter, host = _preparation_context(request, host_config_path, catalog)
    package = None if tasks_only else resolve_installation(
        os.environ.get('FRUITFLY_EVAL_PACKAGE'), checkout=Path(__file__).resolve().parent.parent)
    return prepare(request, adapter.descriptor, host, package=package, tasks_only=tasks_only, progress=progress)


def check_evaluation(request, *, host_config_path=None, catalog=None):
    from .harbor.preparation import inspect, load_preparation
    adapter, host = _preparation_context(request, host_config_path, catalog)
    if request.benchmark.task_names:
        from .task_selection import select_prepared_tasks
        try:
            receipt = load_preparation(host, adapter.descriptor, request.benchmark.variant)
            selected = select_prepared_tasks(receipt, request.benchmark.task_names)
        except (OSError, ValueError, KeyError) as exc:
            return {'available': False, 'checks': [{'id': 'task_selection', 'status': 'failed', 'detail': str(exc)}]}
        result = inspect(request, adapter.descriptor, host, receipt=receipt)
        return {**result, 'task_count': len(selected['tasks']), 'task_names': list(request.benchmark.task_names)}
    return inspect(request, adapter.descriptor, host)


def _preparation_context(request, host_config_path, catalog):
    from .benchmarks.harbor import HarborBenchmarkAdapter
    from .harbor.host import HostConfig
    adapter = (catalog or builtin_catalog()).get(request.benchmark.benchmark_id)
    if not isinstance(adapter, HarborBenchmarkAdapter):
        raise ValueError('preparation commands require a Harbor adapter')
    if request.benchmark.variant not in {v.variant_id for v in adapter.descriptor.variants}:
        raise ValueError('unknown benchmark variant')
    return adapter, HostConfig.read(Path(request.runtime.working_directory).resolve(), host_config_path)


def evaluation_directory(output_root, evaluation_id):
    if (not isinstance(evaluation_id, str) or Path(evaluation_id).name != evaluation_id
            or evaluation_id in {'', '.', '..'}):
        raise ValueError('invalid evaluation ID')
    root = Path(output_root).resolve()
    path = root / evaluation_id
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError('evaluation record escapes output root')
    return path


def stop_evaluation(evaluation_id, *, output_root):
    from .harbor.lifecycle import request_stop
    return request_stop(evaluation_directory(output_root, evaluation_id))


def read_report(evaluation_id, *, output_root, as_json=True):
    root = evaluation_directory(output_root, evaluation_id)
    return json.loads((root / 'report.json').read_text(encoding='utf-8')) if as_json else (root / 'report.md').read_text(encoding='utf-8')
