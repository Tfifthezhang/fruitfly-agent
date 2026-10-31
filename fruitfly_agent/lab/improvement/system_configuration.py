"""Editor/evaluator surfaces and fixed experiment policy normalization."""
from dataclasses import asdict
from typing import Any, Callable

from fruitfly_agent.lab.catalog.configuration import ConfigurationSurface
from fruitfly_agent.runtime_spec.documents import mapping
from .assessment.instructions import EvaluatorInstructions, EvaluatorInstructionTarget
from .editor.instructions import EditorInstructions
from .configuration import ImprovementSettings
from .strategies.exploration import ExplorationSettings, validate_exploration, builtin_explorations


def editor_parameters(parameters):
    mapping(parameters, {'model_role', 'instructions'}, 'editor parameters')
    if parameters.get('model_role', 'editor') != 'editor':
        raise ValueError('editor model_role must be editor')
    value = parameters.get('instructions', {})
    mapping(value, EditorInstructions.__dataclass_fields__, 'editor instructions')
    return {'model_role': 'editor',
            'instructions': asdict(EditorInstructions(**value))}


def feedback_parameters(parameters):
    mapping(parameters, {'evidence'}, 'assessment')
    evidence = mapping(parameters.get('evidence', {}), {'page_characters'}, 'evidence')
    page = evidence.get('page_characters', 12000)
    if type(page) is not int or not 1 <= page <= 24000:
        raise ValueError('evidence.page_characters must be 1..24000')
    return {'evidence': {'page_characters': page}}


def search_parameters(parameters):
    allowed = {'strategy', 'generator', 'rounds', 'mode', 'width', 'exploration', 'retain_experience',
               'sampling', 'promotion_every_rounds', 'research', 'progress'}
    mapping(parameters, allowed, 'search parameters')
    values = {key: value for key, value in parameters.items() if key not in {'exploration', 'sampling', 'promotion_every_rounds', 'research', 'progress'}}
    settings = ImprovementSettings(**values)
    policy = parameters.get('exploration', 'incumbent')
    builtin_explorations().get(policy)
    result = {**{key: getattr(settings, key) for key in allowed - {'exploration', 'sampling', 'promotion_every_rounds', 'research', 'progress'}}, 'exploration': policy}
    if 'sampling' in parameters or 'promotion_every_rounds' in parameters:
        from .task_sets.configuration import MultiTaskSettings
        sampling = parameters.get('sampling', {})
        multi = MultiTaskSettings.from_dict({'sampling': sampling,
            'promotion': {'every_rounds': parameters.get('promotion_every_rounds', 3)}})
        result.update(sampling={**asdict(multi.sampling), 'task_keys': list(multi.sampling.task_keys)},
                      promotion_every_rounds=multi.promotion.every_rounds)
    from .workflow.mechanisms import mechanism_parameters
    result.update(mechanism_parameters(parameters))
    return result


def evaluator_parameters(parameters):
    mapping(parameters, {'instructions'}, 'evaluator parameters')
    value = mapping(parameters.get('instructions', {}), EvaluatorInstructions.__dataclass_fields__, 'evaluator instructions')
    return {'instructions': asdict(EvaluatorInstructions(**value))}


def configuration_surfaces():
    return (
        ConfigurationSurface('improvement-editor', 'I', 'settings', 'editor', editor_parameters,
                             edit_options=editor_edit_options, restore=restore_editor),
        ConfigurationSurface('improvement-evaluator', 'I', 'settings', 'evaluator', evaluator_parameters,
                             edit_options=settings_edit_options,
                             restore=lambda parameters, text: {'instructions': asdict(EvaluatorInstructionTarget.parse(text))}))


def restore_editor(parameters, text):
    from .editor.instructions import EditorInstructionTarget
    instructions = EditorInstructionTarget.parse_document(text)
    return {**parameters, 'instructions': asdict(instructions)}


def editor_edit_options(fields, bounds):
    allowed = {'parameters.instructions.' + name for name in EditorInstructions.__dataclass_fields__}
    if set(fields) - allowed or bounds:
        raise ValueError('editor grants select instruction fields only')
    return {'editable_fields':list(fields)}


def settings_edit_options(fields, bounds):
    if any(not name.startswith('parameters.') for name in fields):
        raise ValueError('I setting grants must select parameters fields')
    return {'editable_fields': list(fields),
            'bounds': dict(bounds)}


def validate_component_options(name, options, inventory):
    from .editor.instructions import EditorInstructionTarget
    targets: dict[str, Callable[[], Any]] = {'improvement-editor': lambda: EditorInstructionTarget(EditorInstructions(**inventory.settings.get('editor', {}).get('instructions', {}))),
        'improvement-evaluator': lambda: EvaluatorInstructionTarget(EvaluatorInstructions(**inventory.settings.get('evaluator', {}).get('instructions', {})))}
    if name not in targets:
        raise ValueError('unknown improvement component options: ' + name)
    targets[name]().validate_options(options)


def exploration_settings(values=None):
    settings = ExplorationSettings((values or {}).get('search', {}).get('exploration', 'incumbent'))
    validate_exploration(settings, builtin_explorations())
    return settings
