"""Resolve experiment documents into typed comparison and execution settings."""
from pathlib import Path

from fruitfly_agent.runtime_spec.documents import DocumentReader, mapping
from fruitfly_agent.lab.catalog import builtin_catalog, load_system_config, edit_grants
from fruitfly_agent.lab.improvement.system_configuration import process_configuration


def normalize_experiment(raw, target, *, material_only=False):
    mapping(raw, {'baseline', 'tasks', 'comparison', 'edit', 'budget', 'trial', 'rsi', 'stop'},
            'experiment')
    baseline = mapping(raw.get('baseline'), {'config', 'profile'}, 'experiment baseline')
    if not isinstance(baseline.get('config'), str) or not baseline['config'].strip():
        raise ValueError('experiment baseline requires config')
    path = (target.parent / baseline['config']).resolve()
    from fruitfly_agent.run.extensions import configured_extensions
    extensions = configured_extensions(path, profile_id=baseline.get('profile')) if not material_only else None
    catalog = extensions.catalog(builtin_catalog()) if extensions is not None else builtin_catalog()
    profile = None if material_only else load_system_config(path, catalog=catalog).select(baseline.get('profile'))
    reader = DocumentReader()
    task, task_path = reader.reference(raw.get('tasks'), target)
    mapping(task, {'source', 'instruction', 'input_paths', 'pack', 'parameters', 'request', 'host',
                   'model_calls', 'collections', 'material'}, 'task document')
    def paths(value):
        result = dict(value)
        for field in ('request', 'host'):
            if field in result:
                result[field] = str((task_path.parent / result[field]).resolve())
        if 'input_paths' in result:
            result['input_paths'] = [str((task_path.parent / name).absolute()) for name in result['input_paths']]
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
    mapping(comparison, {'scope', 'feedback', 'aggregation', 'selection', 'minimum_gain',
                         'max_collection_regression', 'adoption', 'weights'}, 'comparison')
    if comparison.get('adoption', 'none') != 'none':
        raise ValueError('select independent verification through the supported persistent execution policy')
    if comparison.get('selection', 'all') != 'all':
        raise ValueError('comparison selection must be all')
    grants = raw.get('edit')
    options = {} if material_only else edit_grants(profile, grants, catalog)
    search = dict(profile.component_settings.get('search', {})) if profile is not None else {}
    search.pop('exploration', None)
    # These I mechanisms are assembled from the original shared system settings.
    # They are not a second set of experiment allocation fields.
    for name in ('research', 'progress', 'finalization'):
        search.pop(name, None)
    sampling = search.pop('sampling', {})
    promotion_interval = search.pop('promotion_every_rounds', None)
    budget = mapping(raw.get('budget', {}), {'max_model_calls', 'max_executions', 'timeout_seconds'}, 'budget')
    improvement = {**search, **budget, 'components': list(grants), 'component_options': options,
                   'scope': comparison.get('scope', 'task'), 'feedback': comparison.get('feedback', 'auto')}
    if 'operation_timeout_seconds' in trial:
        improvement['operation_timeout'] = trial['operation_timeout_seconds']
    from fruitfly_agent.lab.improvement.system_configuration import process_settings_values
    process, exploration = process_configuration(profile) if profile is not None else process_settings_values({})
    from dataclasses import asdict
    runtime = {'config': str(path)}
    if profile is not None or baseline.get('profile'):
        runtime['profile'] = profile.profile_id if profile is not None else baseline['profile']
    normalized = {'task': task, 'runtime': runtime,
                  'improvement': improvement, 'process_assessment': {**asdict(process), 'assessors': list(process.assessors)},
                  'exploration': asdict(exploration),
                  'models': {key: value for key, value in profile.model_roles.items() if key in {'editor', 'assessor'}} if profile is not None else {},
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
    sources = (*(profile.source_files if profile is not None else ()), *reader.sources.values())
    return normalized, sources, {name: str(comparison_path) for name in comparison}
