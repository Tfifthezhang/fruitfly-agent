"""Outer composition of native and optional Eval task collection sources."""
from __future__ import annotations
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING

from fruitfly_agent.lab.improvement.api import (TaskSetSnapshot, TaskSetSourceRegistry,
    task_set_execution, task_set_minimum_budget, sample_batch)
from fruitfly_agent.lab.improvement.task_sets.files import definition as files_definition
from fruitfly_agent.lab.improvement.tasks import TaskPackCatalog
from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts
from fruitfly_agent.improvement.contracts.validation import identifier
from .sources import SourceBinding
if TYPE_CHECKING:
    from .configuration import ExperimentConfig


@dataclass
class TaskSetPreparation:
    snapshot: TaskSetSnapshot | None
    specifications: tuple
    registry: TaskSetSourceRegistry
    config: ExperimentConfig
    bindings: tuple = ()
    runtime_config: Path | None = None
    runtime_profile: str | None = None

    def freeze(self, context):
        context.runtime_config = self.runtime_config
        context.runtime_profile = self.runtime_profile
        return self.registry.freeze(self.specifications, context)

    def definition(self):
        if self.snapshot is None:
            raise ValueError('task set has not been frozen')
        bindings = self.freeze(SimpleNamespace(workspace=self.config.workspace, tasks=TaskPackCatalog(self.config.workspace),
            component_ids=self.config.improvement.components, artifacts=MemoryArtifacts()))
        capabilities = frozenset.intersection(*(b.capabilities for b in bindings))
        roles = frozenset.intersection(*(b.roles for b in bindings))
        return task_set_execution(self.freeze, self.config.multi_task, expected=self.snapshot,
            capabilities=capabilities, roles=roles)


def specifications(config):
    task = config.task
    if set(task) != {'source', 'collections'} or not isinstance(task['collections'], list) or not task['collections']:
        raise ValueError('task-set needs a nonempty collections list')
    rows, names = [], set()
    for item in task['collections']:
        if not isinstance(item, dict) or not {'id', 'source'} <= item.keys():
            raise ValueError('each collection needs id and source')
        identifier(item['id'])
        if item['id'] in names:
            raise ValueError('collection IDs must be distinct')
        names.add(item['id'])
        row = dict(item)
        for key in ('request', 'host'):
            if key in row:
                row[key] = str(config.resolve(row[key]))
        if row['source'] == 'eval':
            from eval.improvement.configuration import resolve_benchmark
            benchmark = resolve_benchmark(replace(config, task={key: value for key, value in row.items()
                if key in {'source', 'request', 'host', 'model_calls'}}))
            row['request'] = str(benchmark.source_request)
            row['host'] = str(benchmark.require_host())
        rows.append(row)
    return tuple(rows)


def prepare_collections(config, *, tasks_only=False, progress=None):
    """Only the explicit Eval prepare action calls these external operations."""
    from eval.improvement.configuration import resolve_benchmark
    from eval.api import prepare_evaluation
    result = {}
    for row in config.task.get('collections', ()):
        if row.get('source') == 'eval':
            benchmark = resolve_benchmark(replace(config, task={key: value for key, value in row.items()
                if key in {'source', 'request', 'host', 'model_calls'}}))
            result[row['id']] = prepare_evaluation(benchmark.request,
                host_config_path=benchmark.stage_host(), tasks_only=tasks_only, progress=progress)
    if not result:
        raise ValueError('task set contains no Eval collections to prepare')
    return {'collections': result}


def registry_for(rows):
    registry = TaskSetSourceRegistry((files_definition(),))
    if any(row['source'] == 'eval' for row in rows):
        from eval.improvement.task_sets import definition
        registry.register(definition())
    return registry


def resolve(config):
    rows = specifications(config)
    registry = registry_for(rows)
    from fruitfly_agent.runtime_spec import runtime_reference
    path = config.resolve(config.runtime['config']) if 'config' in config.runtime else None
    profile = config.runtime.get('profile')
    for row in rows:
        if row['source'] == 'eval':
            from eval.contracts import EvaluationRequest
            runtime = EvaluationRequest.read(row['request']).runtime
            path, profile = runtime_reference(config.workspace, runtime.config_path, runtime.profile,
                inherited_path=path, inherited_profile=profile)
    path, profile = runtime_reference(config.workspace, inherited_path=path, inherited_profile=profile)
    preparation = TaskSetPreparation(None, rows, registry, config, runtime_config=path, runtime_profile=profile)
    bindings = preparation.freeze(SimpleNamespace(workspace=config.workspace, tasks=TaskPackCatalog(config.workspace),
        component_ids=config.improvement.components, artifacts=MemoryArtifacts()))
    snapshot = TaskSetSnapshot(tuple(e for b in bindings for e in b.entries))
    preparation.snapshot = snapshot
    preparation.bindings = bindings
    batch = sample_batch(snapshot, config.multi_task.sampling, 0, attempts=config.multi_task.execution.attempts)
    minimum = task_set_minimum_budget(snapshot, config.multi_task)
    from fruitfly_agent.lab.improvement.assessment.joint import assess_batch
    assess_batch(snapshot, batch, (), config.multi_task.evaluation)
    if config.improvement.strategy != 'simple' or config.improvement.retain_experience:
        raise ValueError('task-set search currently needs simple search without experience retention')
    if config.improvement.feedback == 'behavior':
        raise ValueError('joint task-set search needs declared task objectives')
    return SourceBinding('task-set', 'task-set', measured=True, source_identity=snapshot.snapshot_id,
        minimum_budget=minimum, adoption_notice='joint development scores need an independently registered adoption verifier',
        config_path=path, profile=profile,
        defaults={'max_model_calls': max(256, minimum['model'] * 2),
                  'max_executions': max(16, minimum['execution'] * 2)}, task_set=preparation)
