"""Shared typed-parameter declarations for context owners, without a registry."""
from dataclasses import fields
from fruitfly_agent.core.mechanisms import ParameterDescriptor, ParameterKind


def parameters(config_type):
    defaults = config_type()
    result = []
    for item in fields(defaults):
        value = getattr(defaults, item.name)
        kind: ParameterKind = 'boolean' if type(value) is bool else 'integer' if type(value) is int else 'number' if type(value) is float else 'string'
        result.append(ParameterDescriptor(item.name, kind, item.name.replace('_', ' ').capitalize(),
            'Owner-validated context policy parameter.', value, advanced=True))
    return tuple(result)


def validate(config_type, values):
    try:
        config_type(**values)
    except TypeError as exc:
        raise ValueError('unknown context policy parameter: ' + ', '.join(sorted(set(values) - {f.name for f in fields(config_type)}))) from exc
