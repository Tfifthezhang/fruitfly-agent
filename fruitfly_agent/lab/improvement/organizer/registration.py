"""Organizer configuration joins the existing Catalog surface declaration."""
from dataclasses import asdict
import json
from fruitfly_agent.lab.catalog.configuration import ConfigurationSurface
from fruitfly_agent.runtime_spec.documents import mapping, parameter_default
from .instructions import OrganizerInstructions, instruction_target


def normalize(parameters):
    mapping(parameters, {'instructions', 'settings'}, 'organizer parameters')
    value = mapping(parameters.get('instructions', {}), OrganizerInstructions.__dataclass_fields__, 'organizer instructions')
    settings = mapping(parameters.get('settings', {}), {'events_per_unit', 'extraction_model_requests'}, 'organizer settings')
    limit = settings.get('events_per_unit', parameter_default(
        __package__ + '.methods.layered', 'defaults.yaml', 'settings.events_per_unit'))
    if type(limit) is not int or not 1 <= limit <= 128:
        raise ValueError('organizer events_per_unit must be between 1 and 128')
    requests = settings.get('extraction_model_requests', parameter_default(
        __package__ + '.methods.layered', 'defaults.yaml', 'settings.extraction_model_requests'))
    if type(requests) is not int or not 0 <= requests <= 4096:
        raise ValueError('organizer extraction_model_requests must be between 0 and 4096')
    return {'instructions': asdict(OrganizerInstructions(**value)),
            'settings': {'events_per_unit': limit, 'extraction_model_requests': requests}}


def edit_options(fields, bounds):
    options = {'editable_fields': list(fields), 'bounds': bounds}
    instruction_target().validate_options(options)
    return {'editable_fields': list(fields)}


def target(state, context, parameters):
    reference = context.artifact_bindings.get('improvement-organizer')
    text = context.artifact_reader(reference) if reference else None
    owner = instruction_target(OrganizerInstructions(**parameters['instructions']))
    return instruction_target(owner.parse(text) if text else owner.instructions, text=text)


def restore(parameters, text):
    return {**parameters, **json.loads(text)}


def surface():
    return ConfigurationSurface('improvement-organizer', 'I', 'settings', 'organizer', normalize,
        edit_options=edit_options, restore=restore, standalone=True,
        default_resource=('fruitfly_agent.lab.improvement.organizer.methods.layered', 'defaults.yaml'),
        optimization=instruction_target().optimization, target_factory=target,
        kind='improvement-instructions', schema='role-instructions-v1', artifact_slot='improvement-organizer')
