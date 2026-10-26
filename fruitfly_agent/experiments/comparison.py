"""Resolve schema-2 experiment references into existing public comparison ports."""
from pathlib import Path

from fruitfly_agent.runtime_spec.documents import DocumentReader, mapping
from fruitfly_agent.lab.catalog import builtin_catalog, load_system_config, edit_grants
from fruitfly_agent.lab.improvement.system_configuration import process_configuration


def normalize_experiment(raw, target):
    mapping(raw, {'schema_version', 'baseline', 'tasks', 'comparison', 'edit', 'budget', 'trial', 'rsi', 'stop'},
            'experiment')
    baseline = mapping(raw.get('baseline'), {'config', 'profile'}, 'experiment baseline')
    if not isinstance(baseline.get('config'), str) or not baseline['config'].strip():
        raise ValueError('experiment baseline requires config')
    path = (target.parent / baseline['config']).resolve()
    catalog = builtin_catalog()
    profile = load_system_config(path, catalog=catalog).select(baseline.get('profile'))
    reader = DocumentReader()
    task, task_path = reader.reference(raw.get('tasks'), target)
    if not isinstance(task, dict) or type(task.get('schema_version')) is not int or task['schema_version'] != 1:
        raise ValueError('task document requires schema_version 1')
    task = {key: value for key, value in task.items() if key != 'schema_version'}
    def paths(value):
        result = dict(value)
        for field in ('request', 'host'):
            if field in result:
                result[field] = str((task_path.parent / result[field]).resolve())
        if 'input_paths' in result:
            result['input_paths'] = [str((task_path.parent / name).resolve()) for name in result['input_paths']]
        return result
    task = paths(task)
    trial = mapping(raw.get('trial', {}), {'model_calls', 'operation_timeout_seconds', 'attempts', 'concurrency'}, 'trial')
    if 'collections' in task:
        task['collections'] = [paths(row) for row in task['collections']]
        for row in task['collections']:
            if 'model_calls' in trial or row.get('source') == 'eval':
                row['model_calls'] = trial.get('model_calls', 80)
    elif task.get('source') == 'eval':
        task['model_calls'] = trial.get('model_calls', 80)
    elif task.get('source') == 'files' and 'model_calls' in trial:
        task['parameters'] = {**task.get('parameters', {}), 'model_calls': trial['model_calls']}
    elif 'model_calls' in trial:
        raise ValueError('editor studies use their explicit inner/evaluation model allowances')
    comparison, comparison_path = reader.reference(raw.get('comparison'), target)
    mapping(comparison, {'schema_version', 'scope', 'feedback', 'aggregation', 'selection', 'minimum_gain',
                         'max_collection_regression', 'adoption', 'weights'}, 'comparison')
    if type(comparison.get('schema_version')) is not int or comparison['schema_version'] != 1:
        raise ValueError('comparison requires schema_version 1')
    if comparison.get('adoption', 'none') != 'none':
        raise ValueError('select independent verification through the supported persistent execution policy')
    if comparison.get('selection', 'all') != 'all':
        raise ValueError('comparison selection must be all')
    grants = raw.get('edit')
    options = edit_grants(profile, grants, catalog)
    search = dict(profile.component_settings.get('search', {}))
    search.pop('exploration', None)
    sampling = search.pop('sampling', {})
    promotion_interval = search.pop('promotion_every_rounds', None)
    budget = mapping(raw.get('budget', {}), {'max_model_calls', 'max_executions', 'timeout_seconds'}, 'budget')
    improvement = {**search, **budget, 'components': list(grants), 'component_options': options,
                   'scope': comparison.get('scope', 'task'), 'feedback': comparison.get('feedback', 'auto')}
    if 'operation_timeout_seconds' in trial:
        improvement['operation_timeout'] = trial['operation_timeout_seconds']
    process, exploration = process_configuration(profile)
    from dataclasses import asdict
    normalized = {'schema_version': 1, 'task': task, 'runtime': {'config': str(path), 'profile': profile.profile_id},
                  'improvement': improvement, 'process_assessment': {**asdict(process), 'assessors': list(process.assessors)},
                  'exploration': asdict(exploration),
                  'models': {key: value for key, value in profile.model_roles.items() if key in {'editor', 'assessor'}},
                  'rsi': raw.get('rsi', {}), 'stop': raw.get('stop', {})}
    if task.get('source') == 'task-set':
        normalized['multi_task'] = {'execution': {key: trial[key] for key in ('attempts', 'concurrency') if key in trial},
            'evaluation': {key: comparison[key] for key in ('aggregation', 'weights') if key in comparison},
            'promotion': {key: comparison[key] for key in ('minimum_gain', 'max_collection_regression') if key in comparison}}
        if sampling:
            normalized['multi_task']['sampling'] = sampling
        if promotion_interval is not None:
            normalized['multi_task']['promotion']['every_rounds'] = promotion_interval
    elif sampling or promotion_interval is not None or any(key in trial for key in ('attempts', 'concurrency')):
        raise ValueError('sampling, attempts and concurrency require a task-set source')
    sources = (*profile.source_files, *reader.sources.values())
    return normalized, sources, {name: str(comparison_path) for name in comparison}
