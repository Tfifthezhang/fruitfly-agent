"""Owner declarations for the editor, feedback and search configuration surfaces."""
from dataclasses import asdict
from typing import Any, Callable

from fruitfly_agent.lab.catalog.configuration import ConfigurationSurface
from fruitfly_agent.runtime_spec.documents import mapping
from .editor.instructions import EditorInstructions
from .configuration import ImprovementSettings
from .assessment.configuration import ProcessAssessmentSettings
from .strategies.exploration import ExplorationSettings, validate_process_configuration, builtin_explorations
from .assessment.registry import builtin_completed_assessors


def editor_parameters(parameters):
    mapping(parameters, {'model_role', 'max_tool_calls', 'max_turns', 'instructions'}, 'editor parameters')
    if parameters.get('model_role', 'editor') != 'editor':
        raise ValueError('editor model_role must be editor')
    calls = parameters.get('max_tool_calls', 48)
    if type(calls) is not int or not 1 <= calls <= 256:
        raise ValueError('editor max_tool_calls must be 1..256')
    turns = parameters.get('max_turns', 12)
    if type(turns) is not int or not 1 <= turns <= 256:
        raise ValueError('editor max_turns must be 1..256')
    value = parameters.get('instructions', {})
    mapping(value, EditorInstructions.__dataclass_fields__, 'editor instructions')
    return {'model_role': 'editor', 'max_tool_calls': calls, 'max_turns': turns,
            'instructions': asdict(EditorInstructions(**value))}


def feedback_parameters(parameters):
    mapping(parameters, {'evidence', 'process_assessment', 'judgment_guidance', 'comparison_guidance'}, 'feedback parameters')
    evidence = mapping(parameters.get('evidence', {}), {'projection', 'page_characters', 'access_mode'}, 'evidence')
    projection = evidence.get('projection', 'granted-full')
    from .evidence.projections import builtin_evidence_projections
    builtin_evidence_projections().get(projection)
    access = evidence.get('access_mode', 'search')
    if access not in {'paged', 'search'}:
        raise ValueError('evidence access_mode must be paged or search')
    page = evidence.get('page_characters', 12000)
    if type(page) is not int or not 1 <= page <= 24000:
        raise ValueError('evidence page_characters must be 1..24000')
    assessment = dict(mapping(parameters.get('process_assessment', {}),
        {*ProcessAssessmentSettings.__dataclass_fields__, 'model_role'}, 'process assessment'))
    if assessment.pop('model_role', 'assessor') != 'assessor':
        raise ValueError('assessment model_role must be assessor')
    settings = ProcessAssessmentSettings(**assessment)
    for name in settings.assessors:
        builtin_completed_assessors().get(name)
    guidance = {key: parameters.get(key, '') for key in ('judgment_guidance', 'comparison_guidance')}
    if any(not isinstance(value, str) or len(value) > 16000 for value in guidance.values()):
        raise ValueError('assessment guidance must be text of at most 16000 characters')
    return {'evidence': {'projection': projection, 'page_characters': page, 'access_mode': access},
            'process_assessment': {**asdict(settings), 'model_role': 'assessor'}, **guidance}


def search_parameters(parameters):
    allowed = {'strategy', 'generator', 'rounds', 'mode', 'width', 'exploration', 'retain_experience',
               'sampling', 'promotion_every_rounds', 'research', 'progress', 'finalization'}
    mapping(parameters, allowed, 'search parameters')
    values = {key: value for key, value in parameters.items() if key not in {'exploration', 'sampling', 'promotion_every_rounds', 'research', 'progress', 'finalization'}}
    settings = ImprovementSettings(**values)
    policy = parameters.get('exploration', 'incumbent')
    builtin_explorations().get(policy)
    result = {**{key: getattr(settings, key) for key in allowed - {'exploration', 'sampling', 'promotion_every_rounds', 'research', 'progress', 'finalization'}}, 'exploration': policy}
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


def configuration_surfaces():
    return (
        ConfigurationSurface('improvement-editor', 'I', 'settings', 'editor', editor_parameters,
                             edit_options=editor_edit_options,
                             restore=restore_editor),
        ConfigurationSurface('improvement-feedback', 'I', 'settings', 'feedback', feedback_parameters,
                             edit_options=settings_edit_options),
        ConfigurationSurface('improvement-search', 'I', 'settings', 'search', search_parameters,
                             edit_options=settings_edit_options))


def restore_editor(parameters, text):
    from .editor.instructions import EditorInstructionTarget
    instructions, calls, turns = EditorInstructionTarget.parse_document(text)
    return {**parameters, 'instructions': asdict(instructions), 'max_tool_calls': calls, 'max_turns': turns}


def editor_edit_options(fields, bounds):
    prefix = 'parameters.instructions.'
    allowed = {'propose', 'invariant', 'domain', 'compose'}
    values = []
    for name in fields:
        if name in {'parameters.max_tool_calls', 'parameters.max_turns'}:
            values.append(name.removeprefix('parameters.'))
        elif name.startswith(prefix) and name[len(prefix):] in allowed:
            values.append(name[len(prefix):])
        else:
            raise ValueError('editor grants must select mutable instructions or tool/turn allowances')
    if set(bounds) - {'parameters.max_tool_calls', 'parameters.max_turns'}:
        raise ValueError('editor bounds require tool/turn allowances')
    return {'editable_fields': values, 'bounds': {k.removeprefix('parameters.'): v for k, v in bounds.items()}}


def settings_edit_options(fields, bounds):
    if any(not name.startswith('parameters.') for name in fields):
        raise ValueError('I setting grants must select parameters fields')
    return {'editable_fields': [name.removeprefix('parameters.') for name in fields],
            'bounds': {name.removeprefix('parameters.'): value for name, value in bounds.items()}}


def validate_component_options(name, options, inventory):
    from .components.configuration import ImprovementSettingsTarget
    from .editor.instructions import EditorInstructionTarget
    targets: dict[str, Callable[[], Any]] = {'improvement-editor': lambda: EditorInstructionTarget(EditorInstructions(**inventory.settings.get('editor', {}).get('instructions', {})), max_tool_calls=inventory.settings.get('editor', {}).get('max_tool_calls', 48), max_turns=inventory.settings.get('editor', {}).get('max_turns', 12)),
               'improvement-feedback': lambda: ImprovementSettingsTarget('feedback', inventory.settings.get('feedback', {})),
               'improvement-search': lambda: ImprovementSettingsTarget('search', inventory.settings.get('search', {}))}
    if name not in targets:
        raise ValueError('unknown improvement component options: ' + name)
    targets[name]().validate_options(options)


def process_configuration(profile):
    return process_settings_values(profile.component_settings)


def process_settings_values(values):
    """Return declared settings without constructing an editor or assessor."""
    feedback = values.get('feedback', {})
    assessment = {key: value for key, value in feedback.get('process_assessment', {}).items() if key != 'model_role'}
    settings = ProcessAssessmentSettings(**assessment)
    exploration = ExplorationSettings(values.get('search', {}).get('exploration', 'incumbent'))
    validate_process_configuration(settings, exploration, builtin_completed_assessors(), builtin_explorations())
    return settings, exploration
