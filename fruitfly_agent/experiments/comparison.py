"""Resolve one experiment grammar into fixed execution, evidence and assessment conditions."""
from fruitfly_agent.runtime_spec.documents import DocumentReader, mapping
from fruitfly_agent.lab.catalog import builtin_catalog, load_system_config, edit_grants
from fruitfly_agent.lab.improvement.configuration import ImprovementSettings
from fruitfly_agent.lab.improvement.evidence.configuration import EvidenceSettings
from fruitfly_agent.improvement.contracts.plans import StageTimeouts
from dataclasses import asdict


def normalize_experiment(raw, target, *, material_only=False):
    mapping(raw, {'baseline', 'tasks', 'edit', 'execution', 'evidence', 'evaluation', 'stopping', 'rsi'}, 'experiment')
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
    mapping(task, {'source', 'instruction', 'input_paths', 'pack', 'parameters', 'request', 'host', 'collections', 'material'}, 'task document')
    def paths(value):
        if not isinstance(value, dict):
            raise ValueError('task and collection documents must be mappings')
        result = dict(value)
        for name in ('request', 'host'):
            if name in result:
                if not isinstance(result[name], str) or not result[name].strip():
                    raise ValueError('task reference paths must be nonempty strings')
                result[name] = str((task_path.parent / result[name]).resolve())
        if 'input_paths' in result:
            if not isinstance(result['input_paths'], list) or any(not isinstance(name, str) or not name.strip() for name in result['input_paths']):
                raise ValueError('task input_paths must be a list of nonempty strings')
            result['input_paths'] = [str((task_path.parent / name).absolute()) for name in result['input_paths']]
        return result
    task = paths(task)
    if 'collections' in task:
        if not isinstance(task['collections'], list) or not task['collections']:
            raise ValueError('task collections must be a nonempty list')
        task['collections'] = [paths(row) for row in task['collections']]
    execution = mapping(raw.get('execution', {}), {'generator', 'editor_seconds', 'task_seconds', 'retain_experience', 'direction', 'trial', 'sampling', 'promotion_every_rounds'}, 'execution')
    evaluation = mapping(raw.get('evaluation', {}), {'evaluator_seconds', 'scope', 'comparison'}, 'evaluation')
    comparison = mapping(evaluation.get('comparison', {}), {'minimum_gain', 'max_collection_regression', 'aggregation', 'weights'}, 'evaluation.comparison')
    stopping = mapping(raw.get('stopping', {}), {'max_rounds', 'no_improvement_rounds', 'consecutive_failures'}, 'stopping')
    for name, value in stopping.items():
        if type(value) is not int or value < (1 if name == 'max_rounds' else 0):
            raise ValueError('stopping limits must be nonnegative integers; max_rounds must be positive')
    timeouts = StageTimeouts(execution.get('editor_seconds', 1200), execution.get('task_seconds', 3600), evaluation.get('evaluator_seconds', 1200))
    grants = raw.get('edit', {})
    if not isinstance(grants, dict):
        raise ValueError('edit must map component IDs to field grants')
    options = {} if material_only or not grants else edit_grants(profile, grants, catalog)
    improvement = asdict(ImprovementSettings(components=tuple(grants), component_options=options,
        generator=execution.get('generator', 'agent-editor-v1'), rounds=stopping.get('max_rounds', 1),
        scope=evaluation.get('scope', 'task'), direction=execution.get('direction', ''),
        retain_experience=execution.get('retain_experience', False), timeouts=timeouts))
    improvement['components'] = list(grants)
    runtime = {'config': str(path)}
    if profile is not None or baseline.get('profile'):
        runtime['profile'] = profile.profile_id if profile is not None else baseline['profile']
    evidence = EvidenceSettings.from_dict(raw.get('evidence')).to_dict()
    normalized = {'task': task, 'runtime': runtime, 'improvement': improvement,
        'models': {k: v for k, v in profile.model_roles.items() if k in {'editor', 'assessor'}} if profile is not None else {},
        'workflow_settings': dict(stopping), 'evidence_settings': evidence,
        'rsi': raw.get('rsi', {}), 'stop': {}}
    trial = mapping(execution.get('trial', {}), {'attempts', 'concurrency'}, 'execution.trial')
    if task.get('source') == 'task-set':
        normalized['multi_task'] = {'execution': dict(trial),
            'evaluation': {k: comparison[k] for k in ('aggregation', 'weights') if k in comparison},
            'promotion': {k: comparison[k] for k in ('minimum_gain', 'max_collection_regression') if k in comparison}}
        if 'sampling' in execution:
            normalized['multi_task']['sampling'] = execution['sampling']
        if 'promotion_every_rounds' in execution:
            normalized['multi_task']['promotion']['every_rounds'] = execution['promotion_every_rounds']
    elif 'sampling' in execution or 'promotion_every_rounds' in execution or trial:
        raise ValueError('sampling, attempts and concurrency require a task-set source')
    if comparison and task.get('source') != 'task-set':
        raise ValueError('evaluation.comparison requires a task-set source')
    sources = (*(profile.source_files if profile is not None else ()), *reader.sources.values())
    return normalized, sources, {}
