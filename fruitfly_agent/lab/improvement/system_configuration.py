"""Editor/evaluator surfaces and fixed experiment policy normalization."""
from dataclasses import asdict
from typing import Any, Callable

from fruitfly_agent.lab.catalog.configuration import ConfigurationSurface
from fruitfly_agent.runtime_spec.documents import mapping
from .assessment.instructions import EvaluatorInstructions, EvaluatorInstructionTarget
from .editor.instructions import EditorInstructions, EditorInstructionTarget
from .configuration import ImprovementSettings
from .editor.configuration import EditorSettings
from .assessment.configuration import EvaluatorSettings


def editor_parameters(parameters):
    mapping(parameters, {'model_role', 'instructions', 'settings'}, 'editor parameters')
    if parameters.get('model_role', 'editor') != 'editor':
        raise ValueError('editor model_role must be editor')
    value = parameters.get('instructions', {})
    mapping(value, EditorInstructions.__dataclass_fields__, 'editor instructions')
    return {'model_role': 'editor',
            'instructions': asdict(EditorInstructions(**value)), 'settings': asdict(EditorSettings.from_dict(parameters.get('settings')))}






def evaluator_parameters(parameters):
    mapping(parameters, {'instructions', 'settings'}, 'evaluator parameters')
    value = mapping(parameters.get('instructions', {}), EvaluatorInstructions.__dataclass_fields__, 'evaluator instructions')
    return {'instructions': asdict(EvaluatorInstructions(**value)), 'settings': asdict(EvaluatorSettings.from_dict(parameters.get('settings')))}


def configuration_surfaces():
    from .organizer.registration import surface
    return (surface(),
        ConfigurationSurface('improvement-editor', 'I', 'settings', 'editor', editor_parameters,
                             edit_options=editor_edit_options, restore=restore_editor, default_resource=('fruitfly_agent.lab.improvement.editor.methods.workspace', 'defaults.yaml'),
                             standalone=True, optimization=EditorInstructionTarget.optimization,
                             kind='improvement-instructions', schema='editor-instructions', target_factory=editor_target,
                             artifact_slot='improvement-editor'),
        ConfigurationSurface('improvement-evaluator', 'I', 'settings', 'evaluator', evaluator_parameters,
                             edit_options=evaluator_edit_options, default_resource=('fruitfly_agent.lab.improvement.assessment.methods.model', 'defaults.yaml'),
                             restore=restore_evaluator,
                             standalone=True, optimization=EvaluatorInstructionTarget.optimization,
                             kind='evaluator-instructions', schema='evaluator-instructions-v1', target_factory=evaluator_target,
                             artifact_slot='improvement-evaluator'))


def editor_target(state, context, parameters):
    reference = context.artifact_bindings.get('improvement-editor')
    return EditorInstructionTarget(EditorInstructions(**parameters['instructions']),
        text=context.artifact_reader(reference) if reference else None, settings=parameters['settings'])


def evaluator_target(state, context, parameters):
    reference = context.artifact_bindings.get('improvement-evaluator')
    return EvaluatorInstructionTarget(EvaluatorInstructionTarget.parse(context.artifact_reader(reference))
        if reference else EvaluatorInstructions(**parameters['instructions']),
        text=context.artifact_reader(reference) if reference else None, settings=parameters['settings'])


def restore_editor(parameters, text):
    from .editor.instructions import EditorInstructionTarget
    instructions = EditorInstructionTarget.parse_document(text)
    import json
    return {**parameters, 'instructions': asdict(instructions), 'settings': json.loads(text)['settings']}


def editor_edit_options(fields, bounds):
    allowed = {'parameters.instructions.' + name for name in EditorInstructions.__dataclass_fields__}
    if set(fields) - allowed or bounds:
        raise ValueError('editor grants select instruction fields only')
    return {'editable_fields':list(fields)}


def evaluator_edit_options(fields, bounds):
    allowed = {'parameters.instructions.' + name for name in EvaluatorInstructions.__dataclass_fields__}
    if not fields or len(set(fields)) != len(fields) or set(fields) - allowed or bounds:
        raise ValueError('evaluator grants select distinct instruction fields only')
    return {'editable_fields': list(fields)}


def validate_component_options(name, options, inventory):
    from .editor.instructions import EditorInstructionTarget
    targets: dict[str, Callable[[], Any]] = {'improvement-editor': lambda: EditorInstructionTarget(EditorInstructions(**inventory.settings.get('editor', {}).get('instructions', {}))),
        'improvement-evaluator': lambda: EvaluatorInstructionTarget(EvaluatorInstructions(**inventory.settings.get('evaluator', {}).get('instructions', {})))}
    from .organizer.instructions import instruction_target
    targets['improvement-organizer'] = lambda: instruction_target()
    if name not in targets:
        raise ValueError('unknown improvement component options: ' + name)
    targets[name]().validate_options(options)




def restore_evaluator(parameters, text):
    import json
    instructions = EvaluatorInstructionTarget.parse(text)
    return {**parameters, 'instructions': asdict(instructions), 'settings': json.loads(text)['settings']}
