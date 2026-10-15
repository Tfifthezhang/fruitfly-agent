"""Prepare immutable official task sets without Agent execution or invented rewards."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import tomllib

from eval.catalog import builtin_catalog
from eval.evidence import material_hash
from fruitfly_agent.lab.optimization.experiments import TaskReference
from fruitfly_agent.lab.algorithms.versions import canonical_json, content_hash


async def resolve_materials(dataset, task_names, limit, cache):
    # Optional SDK imports stay within the external consumer. Dataset discovery
    # and task download use Harbor 0.23.0's public interfaces, without a Trial.
    from harbor.models.job.config import DatasetConfig  # type: ignore[import-not-found]
    from harbor.tasks.client import TaskClient  # type: ignore[import-not-found]
    name, _, version = dataset.partition('@')
    config = DatasetConfig(name=name, version=version or None, task_names=list(task_names) or None)
    configs = sorted(await config.get_task_configs(), key=lambda item: item.get_task_id().get_name())
    if task_names and {c.get_task_id().get_name() for c in configs} != set(task_names):
        raise ValueError('registry tasks differ from the declared fixed batch')
    selected = configs[:limit]
    if len(selected) != limit:
        raise ValueError('the selected dataset has fewer tasks than requested')
    client = TaskClient()
    result = []
    for task in selected:
        download = await client.download_tasks(task_ids=[task.get_task_id()], overwrite=False, output_dir=cache)
        result.append((task.get_task_id().get_name(), Path(download.results[0].path),
                       task.git_commit_id or getattr(task, 'ref', None) or ''))
    return result


async def prepare_task_set(benchmark_id, variant, task_limit, *, output_root, resolver=resolve_materials, progress=None):
    if type(task_limit) is not int or not 3 <= task_limit <= 12:
        raise ValueError('improvement task sets require 3–12 tasks')
    adapter = builtin_catalog().get(benchmark_id)
    descriptor = adapter.descriptor
    options = {v.variant_id: v for v in descriptor.variants}
    if variant not in options or variant not in {'starter', 'no_gpu'}:
        raise ValueError('this task preparation path supports CPU batches with at least three tasks')
    names = options[variant].task_names
    if names and len(names) != task_limit:
        raise ValueError('fixed task batch size differs from the requested limit')
    preflight = adapter.preflight(variant)
    if not preflight.available:
        raise RuntimeError('benchmark preflight failed: ' + '; '.join(str(c['detail']) for c in preflight.checks if not c['ok']))
    output_root = Path(output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=False)
    if progress is not None:
        progress({'type': 'material_preparation', 'text': 'Downloading and freezing original benchmark tasks; no Agent calls yet.'})
    originals = await resolver(descriptor.dataset, names, task_limit, output_root/'cache')
    tasks, materials = [], {}
    for name, source, revision in originals:
        source = Path(source).resolve()
        digest = material_hash(source)
        config = tomllib.loads((source/'task.toml').read_text(encoding='utf-8'))
        if config.get('steps') or (source/'steps').exists():
            raise ValueError('multi-step task sets are unsupported')
        if config.get('environment', {}).get('gpus', 0):
            raise ValueError('GPU tasks are unsupported by this improvement executor')
        task = TaskReference(descriptor.dataset, name, revision or 'local:'+digest, digest,
            (source/'instruction.md').read_text(encoding='utf-8'),
            'harbor-official:'+content_hash((source/'tests/test.sh').read_text(encoding='utf-8')),
            canonical_json(config.get('environment', {})))
        destination = output_root/'tasks'/digest.removeprefix('sha256:')/name.split('/')[-1]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, destination)
        if material_hash(destination) != digest:
            raise ValueError('copied task material changed')
        tasks.append(task.to_dict())
        materials[task.reference_id] = destination.relative_to(output_root).as_posix()
    if len(tasks) != task_limit or len(materials) != task_limit:
        raise ValueError('task preparation produced an incomplete or duplicate batch')
    payload = {'schema_version': 1, 'benchmark_id': benchmark_id, 'dataset': descriptor.dataset,
               'variant': variant, 'tasks': tasks, 'materials': materials, 'material_root': str(output_root)}
    (output_root/'task-set.json').write_text(canonical_json(payload), encoding='utf-8')
    return payload


def improvement_catalog(catalog):
    payload = catalog.to_dict()
    for benchmark in payload['benchmarks']:
        benchmark['variants'] = [v for v in benchmark['variants'] if v['id'] in {'starter', 'no_gpu'}]
        for variant in benchmark['variants']:
            if not variant.get('task_names'):
                variant['label'] = 'CPU sample · 5 tasks'
                variant['description'] = 'Freeze the first five tasks by exact registry name; split 3 training / 1 selection / 1 confirmation.'
    return payload
