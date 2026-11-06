"""Native tool descriptions and legal parameters share ordinary owner assembly."""
from dataclasses import replace
from fruitfly_agent.core.mechanisms import ParameterDescriptor
from fruitfly_agent.lab.catalog.adapters.parameters import editable_parameters
from fruitfly_agent.runtime_spec.documents import parameter_default
from fruitfly_agent.improvement.contracts.text import validate_text


def native_tool(definition, fields=()):
    resource = definition.default_resource
    if resource is None:
        raise ValueError('native tool owner must register its instruction defaults')
    description = parameter_default(*resource, 'instructions.description')
    original = definition.install
    original_validate = definition.validate_parameters
    def validate(parameters):
        if 'description' in parameters:
            validate_text(parameters['description'])
        if original_validate is not None:
            original_validate({key: value for key, value in parameters.items() if key != 'description'})
    def install(state, context, parameters):
        candidate = original(state, context, {key: value for key, value in parameters.items() if key != 'description'})
        validate_text(parameters['description'])
        tools = tuple(replace(tool, description=parameters['description'])
            if tool.name in definition.descriptor.effects.tools else tool for tool in candidate.config.tools)
        return replace(candidate, config=replace(candidate.config, tools=tools))
    paths = definition.parameter_paths or {p.name: 'settings.' + p.name for p in definition.descriptor.parameters}
    result = replace(definition, install=install, validate_parameters=validate,
        descriptor=replace(definition.descriptor, parameters=(*definition.descriptor.parameters,
            ParameterDescriptor('description', 'string', 'Tool instructions',
                'Model-facing operation description. Schema, permission and implementation are protected.', description))),
        parameter_paths={**paths, 'description': 'instructions.description'})
    return editable_parameters(result, {*fields, 'description'}, default_selected=False)
