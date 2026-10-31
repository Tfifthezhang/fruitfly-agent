"""Resolve experiment documents into typed comparison and execution settings."""
from pathlib import Path

from fruitfly_agent.runtime_spec.documents import DocumentReader, mapping
from fruitfly_agent.lab.catalog import builtin_catalog, load_system_config, edit_grants


def normalize_experiment(raw, target, *, material_only=False):
    mapping(raw, {'baseline', 'tasks', 'comparison', 'edit', 'timeouts', 'trial', 'rsi', 'stop', 'search', 'assessment'},
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
                   'collections', 'material'}, 'task document')
    def paths(value):
        result = dict(value)
        for field in ('request', 'host'):
            if field in result:
                result[field] = str((task_path.parent / result[field]).resolve())
        if 'input_paths' in result:
            result['input_paths'] = [str((task_path.parent / name).absolute()) for name in result['input_paths']]
        return result
    task = paths(task)
    trial = mapping(raw.get('trial', {}), {'attempts', 'concurrency'}, 'trial')
    if 'collections' in task:
        task['collections'] = [paths(row) for row in task['collections']]
    comparison, comparison_path = reader.reference(raw.get('comparison'), target)
    mapping(comparison, {'scope', 'feedback', 'aggregation', 'selection', 'minimum_gain',
                         'max_collection_regression', 'adoption', 'weights'}, 'comparison')
    if comparison.get('adoption', 'none') != 'none':
        raise ValueError('select independent verification through the supported persistent execution policy')
    if comparison.get('selection', 'all') != 'all':
        raise ValueError('comparison selection must be all')
    grants = raw.get('edit', {})
    if not isinstance(grants, dict):
        raise ValueError('edit must map component IDs to field grants')
    options = {} if material_only or not grants else edit_grants(profile, grants, catalog)
    from fruitfly_agent.lab.improvement.system_configuration import search_parameters, feedback_parameters
    search = search_parameters(raw.get('search', {}))
    fixed_workflow = {key: search[key] for key in ('research', 'progress')}
    assessment = feedback_parameters(raw.get('assessment', {}))
    exploration_policy = search.pop('exploration')
    # These I mechanisms are assembled from the original shared system settings.
    # They are not a second set of experiment allocation fields.
    for name in ('research', 'progress'):
        search.pop(name, None)
    sampling = search.pop('sampling', {})
    promotion_interval = search.pop('promotion_every_rounds', None)
    from fruitfly_agent.improvement.contracts.plans import StageTimeouts
    from dataclasses import asdict
    timeouts = StageTimeouts(**mapping(raw.get('timeouts', {}), set(StageTimeouts.__dataclass_fields__), 'timeouts'))
    improvement = {**search, 'timeouts': asdict(timeouts), 'components': list(grants), 'component_options': options,
                   'scope': comparison.get('scope', 'task'), 'feedback': comparison.get('feedback', 'auto')}
    from fruitfly_agent.lab.improvement.system_configuration import exploration_settings
    exploration = exploration_settings({'search': {'exploration': exploration_policy}})
    runtime = {'config': str(path)}
    if profile is not None or baseline.get('profile'):
        runtime['profile'] = profile.profile_id if profile is not None else baseline['profile']
    normalized = {'task': task, 'runtime': runtime,
                  'improvement': improvement,
                  'exploration': asdict(exploration),
                  'models': {key: value for key, value in profile.model_roles.items() if key in {'editor', 'assessor'}} if profile is not None else {},
                  'workflow_settings': fixed_workflow, 'evidence_settings': assessment['evidence'],
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
