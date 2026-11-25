"""Prepare official WorkBuddy datasets using an explicitly isolated engine."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

from fruitfly_eval.backends.isolated import IsolatedPython
from fruitfly_eval.benchmarks.base import BenchmarkDescriptor, ProgressSink
from fruitfly_eval.contracts import EvaluationRequest
from fruitfly_eval.harbor.host import HostConfig
from fruitfly_eval.harbor.material import digest, tree_identity, prepare_material, check_material, write_json
from fruitfly_eval.harbor.dependencies import prepare_dependencies, check_dependencies
from fruitfly_eval.harbor.selection import inspect_images
from fruitfly_eval.harbor.docker import image_identity
from .configuration import RunnerSettings
from .tasks import freeze_dataset, inventory, check_dataset, validate_tree


def settings(host: HostConfig) -> RunnerSettings:
    if host.backend_file is None:
        raise ValueError('WorkBuddy requires backend.file referencing its isolated runner settings')
    result = RunnerSettings.read(host.backend_file)
    result.validate()
    return result


def engine(host: HostConfig, *, source: Path | None = None) -> IsolatedPython:
    runner = settings(host)
    return IsolatedPython(runner.python, 'fruitfly_eval.workbuddy.worker',
        ((source or Path(__file__).resolve().parents[2]).resolve(), (runner.checkout / 'src').resolve()))


def receipt_path(host: HostConfig, descriptor: BenchmarkDescriptor, variant: str) -> Path:
    selection = next(v for v in descriptor.variants if v.variant_id == variant)
    key = digest({'dataset': descriptor.dataset, 'version': descriptor.version,
                  'variant': variant, 'tasks': selection.task_names})
    return host.cache / 'workbuddy/preparations' / (key + '.json')


class ResourceInspector:
    def __init__(self, host: HostConfig, client: IsolatedPython):
        self.client, self.checkout = client, str(settings(host).checkout)
        self.cache: dict[str, dict[str, Any]] = {}

    def __call__(self, task: dict[str, Any]) -> dict[str, Any]:
        path = Path(task['path']).resolve()
        key = str(path)
        if key not in self.cache:
            tasks = sorted(str(p.parent.resolve()) for p in path.parent.glob('*/task.toml'))
            response = self.client.call('resources', {'checkout': self.checkout, 'tasks': tasks})
            self.cache.update(response['resources'])
        return self.cache[key]


def normalized_dataset(host: HostConfig, descriptor: BenchmarkDescriptor, variant: str,
                       client: IsolatedPython, bench: dict[str, Any], *, names: tuple[str, ...] = ()) -> dict[str, Any]:
    if host.task_directory is None:
        raise ValueError('WorkBuddy requires task_directory pointing to the complete dataset root')
    inspect = ResourceInspector(host, client)
    original = freeze_dataset(host.task_directory, host.cache / 'workbuddy', descriptor, variant,
                              inspect_resources=inspect)
    runner = settings(host)
    users = {name: bench.get(name) for name in ('agent_user', 'verifier_user')}
    if any(v is not None and not isinstance(v, str) for v in users.values()):
        raise ValueError('official bench user settings must be text or null')
    key = digest({'original': original['sha256'], 'runner': runner.source_sha256, 'users': users})
    parent = host.cache / 'workbuddy/normalized' / key
    target = parent / Path(original['root']).name
    if not parent.exists():
        parent.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.normalize-', dir=parent.parent) as temporary:
            staged = Path(temporary) / key
            staged.mkdir()
            data = staged / target.name
            shutil.copytree(original['root'], data, symlinks=True)
            changes = client.call('normalize', {'checkout': str(runner.checkout), 'dataset': str(data), **users})
            validate_tree(data)
            write_json(staged / 'identity.json', {'sha256': tree_identity(data), 'changes': changes})
            try:
                staged.rename(parent)
            except FileExistsError:
                pass
    saved = json.loads((parent / 'identity.json').read_text())
    if tree_identity(target) != saved['sha256']:
        raise ValueError('normalized dataset changed; do not repair frozen material in place')
    excluded: list[dict[str, Any]] = []
    rows = inventory(target, descriptor, variant, inspect_resources=inspect, excluded=excluded)
    if names:
        from fruitfly_eval.task_selection import select_prepared_tasks
        excluded.extend({'id': row['id'], 'reason': 'outside explicit task_names'} for row in rows if row['id'] not in names)
        rows = select_prepared_tasks({'id': saved['sha256'], 'tasks': rows}, names)['tasks']
    return {'root': str(target), 'sha256': saved['sha256'], 'original': original,
            'dataset': descriptor.dataset, 'variant': variant, 'tasks': rows, 'task_names': list(names),
            'normalization': saved['changes'], 'excluded': excluded}


class WorkBuddyPreparation:
    def read_host(self, workspace: Path, path: str | Path | None) -> HostConfig:
        host = HostConfig.read(workspace, path)
        settings(host)
        return host

    def prepare(self, request: EvaluationRequest, descriptor: BenchmarkDescriptor, host: HostConfig, *,
                package: Path | None, tasks_only: bool, progress: ProgressSink | None) -> dict[str, Any]:
        if host.task_patches:
            raise ValueError('WorkBuddy uses its official normalization; arbitrary verifier patches are unsupported')
        runner, client = settings(host), engine(host)
        state = client.call('describe', {'checkout': str(runner.checkout)})
        bench = client.call('bench', {'checkout': str(runner.checkout), 'dataset': str(host.task_directory)})['bench']
        if bench.get('llm_judge', {}).get('enabled'):
            raise ValueError('this adapter does not yet support an independent WorkBuddy LLM judge; do not disable official scoring to run it')
        if progress:
            progress({'type': 'preparation', 'stage': 'workbuddy_tasks'})
        dataset = normalized_dataset(host, descriptor, request.benchmark.variant, client, bench,
                                     names=request.benchmark.task_names)
        tasks = dataset['tasks']
        selection = {'dataset': descriptor.dataset, 'variant': request.benchmark.variant,
                     'selected': [r['id'] for r in tasks], 'task_names': list(request.benchmark.task_names),
                     'excluded': dataset['excluded']}
        overview = {'task_count': len(tasks), 'selection': selection, 'images': inspect_images(tasks, 'docker')}
        if tasks_only:
            path = host.cache / 'workbuddy/inventory' / (digest(selection) + '.json')
            write_json(path, {**overview, 'dataset': dataset})
            return {**overview, 'inventory': str(path), 'detail': 'Tasks only; runtime, verifier and model unverified'}
        if package is None:
            raise ValueError('full preparation requires complete Agent installation material')
        runtime = prepare_material(host, package)
        dependencies = prepare_dependencies(host, 'docker')
        client = engine(host, source=Path(runtime['source']))
        probes = []
        from fruitfly_eval.harbor.environments import environment_key
        for task in tasks:
            key = environment_key(task)
            directory = host.cache / 'workbuddy/checks' / key
            if progress:
                progress({'type': 'preparation', 'stage': 'workbuddy_environment', 'task_id': task['id']})
            probes.append(client.call('probe', {'checkout': str(runner.checkout),
                'workspace': request.runtime.working_directory, 'host': str(host.path),
                'task': task, 'runtime': runtime, 'docker': 'docker', 'directory': str(directory)}, timeout=1800))
        receipt = {'schema_version': 1, 'backend': 'workbuddy', 'dataset': descriptor.dataset,
            'variant': request.benchmark.variant, 'host': host.to_dict(), 'runner': runner.validate(),
            'runner_settings': runner.to_dict(), 'engine': state['engine'],
            'controller': state['controller'], 'bench': bench, 'dataset_material': dataset,
            'selection': selection, 'tasks': tasks, 'runtime': runtime, 'dependencies': dependencies,
            'environments': probes}
        receipt['id'] = digest(receipt)
        path = receipt_path(host, descriptor, request.benchmark.variant)
        write_json(path, receipt)
        return {**overview, 'receipt': str(path), 'runtime_id': runtime['id']}

    def load(self, host: HostConfig, descriptor: BenchmarkDescriptor, variant: str) -> dict[str, Any]:
        path = receipt_path(host, descriptor, variant)
        if not path.is_file():
            raise ValueError('WorkBuddy selection is not prepared; run eval prepare')
        receipt = json.loads(path.read_text())
        if (receipt.get('schema_version') != 1 or receipt.get('backend') != 'workbuddy'
                or receipt.get('dataset') != descriptor.dataset or receipt.get('variant') != variant
                or receipt.get('id') != digest({k: v for k, v in receipt.items() if k != 'id'})):
            raise ValueError('WorkBuddy preparation identity changed; prepare again')
        if (receipt['host'] != host.to_dict() or receipt['runner'] != settings(host).validate()
                or receipt['runner_settings'] != settings(host).to_dict()):
            raise ValueError('WorkBuddy runtime settings changed; prepare again')
        check_material(host, receipt['runtime'])
        check_dependencies(host, receipt['dependencies'])
        check_dataset(receipt['dataset_material'], descriptor, variant,
            inspect_resources=ResourceInspector(host, engine(host, source=Path(receipt['runtime']['source']))))
        if receipt['tasks'] != receipt['dataset_material']['tasks']:
            raise ValueError('WorkBuddy task population differs from its frozen dataset')
        return receipt

    def inspect(self, request: EvaluationRequest, descriptor: BenchmarkDescriptor, host: HostConfig, *,
                receipt: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            record = receipt if receipt is not None else self.load(host, descriptor, request.benchmark.variant)
            if record['selection'].get('task_names') and not request.benchmark.task_names:
                raise ValueError('prepared subset requires explicit task_names; prepare the full population to run an unrestricted variant')
            if request.benchmark.task_names:
                from fruitfly_eval.task_selection import select_prepared_tasks
                select_prepared_tasks(record, request.benchmark.task_names)
            runner = settings(host)
            current = engine(host, source=Path(record['runtime']['source'])).call('describe', {'checkout': str(runner.checkout)})
            if current['controller'] != record['controller'] or current['engine'] != record['engine']:
                raise ValueError('isolated engine environment changed; prepare again')
            for probe in record['environments']:
                for image in probe['images']:
                    if image_identity('docker', image['reference']) != image['id']:
                        raise ValueError('prepared image changed: ' + image['reference'])
            for image, identity in record['dependencies']['images'].items():
                if image_identity('docker', image) != identity:
                    raise ValueError('prepared dependency image changed: ' + image)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            return {'available': False, 'checks': [{'id': 'workbuddy_preparation', 'status': 'failed', 'detail': str(exc)}]}
        return {'available': True, 'task_count': len(record['tasks']), 'checks': [
            {'id': 'workbuddy_preparation', 'status': 'passed', 'detail': 'Frozen source, isolated engine and images match'},
            {'id': 'verifier_execution', 'status': 'unverified', 'detail': 'Requires an authorized real smoke'},
            {'id': 'model_connectivity', 'status': 'unverified', 'detail': 'No inference requests made'}]}
