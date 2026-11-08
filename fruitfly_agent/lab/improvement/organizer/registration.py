"""Organizer configuration joins the existing Catalog surface declaration."""
from dataclasses import asdict
from fruitfly_agent.lab.catalog.configuration import ConfigurationSurface
from fruitfly_agent.runtime_spec.documents import mapping
from .instructions import OrganizerInstructions, instruction_target


def normalize(parameters):
    mapping(parameters, {'instructions'}, 'organizer parameters')
    value = mapping(parameters.get('instructions', {}), {'system', 'organize'}, 'organizer instructions')
    return {'instructions': asdict(OrganizerInstructions(**value))}


def edit_options(fields, bounds):
    options = {'editable_fields': list(fields), 'bounds': bounds}
    instruction_target().validate_options(options)
    return {'editable_fields': list(fields)}


def target(state, context, parameters):
    reference = context.artifact_bindings.get('improvement-organizer')
    text = context.artifact_reader(reference) if reference else None
    owner = instruction_target(OrganizerInstructions(**parameters['instructions']))
    return instruction_target(owner.parse(text) if text else owner.instructions, text=text)


def surface():
    return ConfigurationSurface('improvement-organizer', 'I', 'settings', 'organizer', normalize,
        edit_options=edit_options, standalone=True,
        default_resource=('fruitfly_agent.lab.improvement.organizer.methods.layered', 'defaults.yaml'),
        optimization=instruction_target().optimization, target_factory=target,
        kind='improvement-instructions', schema='role-instructions-v1', artifact_slot='improvement-organizer')
