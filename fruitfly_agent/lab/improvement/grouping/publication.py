"""Publish selected records and retain the composition receipt separately."""
from fruitfly_agent.improvement.contracts.research import ResearchBatch
from fruitfly_agent.improvement.contracts.versions import canonical_json, content_hash

from .registration import METHODS, normalize
from .methods.relational import select as related


def compose(pool, source, settings, position, members, *, features=None):
    if type(position) is not int or position < 0:
        raise ValueError('group position must be a nonnegative integer')
    settings = normalize({'settings': settings})['settings']
    tasks = {task.task_id: task for task in pool.tasks}
    method = settings['method']
    if method in METHODS:
        selected = METHODS[method](tasks, members, position, settings['batch_size'], settings['seed'])
    else:
        if members is not None or features is None or set(features) != set(tasks):
            raise ValueError('relation grouping requires a feature table for the exact pool')
        selected = related(tasks, features, method=method, position=position,
                           size=settings['batch_size'], seed=settings['seed'])
    grants = selected if method == 'fixed' else dict.fromkeys(selected)
    runs_by_task = {task: [] for task in grants}
    records = []
    for record in pool.records:
        if record.task_id in grants and (grants[record.task_id] is None or record.run_id in grants[record.task_id]):
            runs_by_task[record.task_id].append(record.run_id)
            records.append(record)
    for task, granted in grants.items():
        if granted is not None and set(granted) != set(runs_by_task[task]):
            raise ValueError('fixed grouping run is outside its task grant')
    run_ids = {record.run_id for record in records}
    observations = tuple(item for item in pool.observations if isinstance(item, dict)
                         and isinstance(item.get('run_id'), str) and item['run_id'] in run_ids
                         and item.get('semantics', {}).get('scope', 'execution') == 'execution')
    batch = ResearchBatch(tuple(tasks[task] for task in selected), tuple(records), observations)
    harnesses = {record.harness_id for record in pool.records}
    parent = {'assurance': 'unknown'}
    if len(harnesses) == 1 and all(task.environment_id != 'retained-eval-evidence' for task in pool.tasks):
        parent = {'assurance': 'recorded', 'harness_id': next(iter(harnesses))}
    decision = {'source_pool': source, 'settings': settings, 'position': position,
                'policy_id': content_hash(canonical_json(settings)),
                'members': [{'task_id': task, 'run_ids': runs_by_task[task]} for task in selected],
                'incomplete_group': len(selected) != settings['batch_size'],
                'coverage': {'pool_tasks': len(tasks), 'chosen_tasks': len(selected),
                             'chosen_runs': len(records), 'tasks_without_runs': sum(not runs for runs in runs_by_task.values())},
                'parent': parent}
    return batch, decision
