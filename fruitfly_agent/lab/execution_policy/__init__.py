"""Object-owned execution configuration, independently editable as H."""
from fruitfly_agent.improvement.contracts.optimization import OptimizationSpec
from dataclasses import replace
import json

from fruitfly_agent.runtime_spec import effective_execution, parse_execution, execution_kwargs
from fruitfly_agent.improvement.contracts.optimization import TargetBinding, TargetSnapshot


class ExecutionPolicyTarget:
    optimization = OptimizationSpec('H', 'parameters', required_capabilities=frozenset({'execution-config'}))
    label = 'Execution policy'
    component_kind = 'execution-policy'
    required_capabilities = frozenset({'execution-config'})

    def __init__(self, config, *, fixed_fields=()):
        self.fixed_fields = frozenset(fixed_fields)
        self.values = effective_execution(config)

    def snapshot(self):
        return TargetSnapshot('execution-policy', json.dumps(self.values, sort_keys=True),
            TargetBinding('configuration', 'execution'), 'execution-policy-v1', 'H')

    def validate(self, text):
        self.validate_change(text, {})

    def prepare_trial(self, config, text):
        return replace(config, **execution_kwargs(parse_execution(text)))

    def validate_options(self, options):
        if not isinstance(options, dict) or set(options) - {'editable_fields', 'bounds'}:
            raise ValueError('execution-policy options need editable_fields/bounds')
        names = set(flatten(self.values)) - self.fixed_fields
        editable = options.get('editable_fields', sorted(names))
        bounds = options.get('bounds', {})
        if (not isinstance(editable, list) or not editable or any(not isinstance(v, str) for v in editable)
                or len(set(editable)) != len(editable) or set(editable) - names or not isinstance(bounds, dict)
                or set(bounds) - set(editable)):
            raise ValueError('execution-policy options cite unsupported fields')
        for key, values in bounds.items():
            if (not isinstance(values, dict) or not values or set(values) - {'minimum', 'maximum'}
                    or any(type(v) is not int for v in values.values())
                    or not isinstance(flatten(self.values)[key], int)
                    or values.get('minimum', 0) > values.get('maximum', float('inf'))):
                raise ValueError('execution-policy bounds must be ordered integer limits')
        self.validate_change(self.snapshot().text, options)

    def validate_change(self, text, options):
        before, after = flatten(self.values), flatten(parse_execution(text))
        editable = set(options.get('editable_fields', set(before) - self.fixed_fields))
        if editable & self.fixed_fields:
            raise ValueError('execution field is controlled by another enabled mechanism')
        if any(after[key] != value for key, value in before.items() if key not in editable):
            raise ValueError('candidate changed a fixed execution field')
        for key, bounds in options.get('bounds', {}).items():
            if not bounds.get('minimum', -float('inf')) <= after[key] <= bounds.get('maximum', float('inf')):
                raise ValueError('candidate execution field exceeds experiment bounds: ' + key)


def flatten(value):
    return {**{key: item for key, item in value.items() if key != 'tool_execution'},
            **{'tool_execution.' + key: item for key, item in value['tool_execution'].items()}}


def validate_component_options(name, options, inventory):
    from types import SimpleNamespace
    if name != 'execution-policy':
        raise ValueError('component does not expose structured options: ' + name)
    target = ExecutionPolicyTarget(SimpleNamespace(**execution_kwargs(inventory.execution)),
        fixed_fields=dict(inventory.execution_owners))
    target.validate_options(options)


def configuration_surface():
    from fruitfly_agent.lab.catalog.configuration import ConfigurationSurface
    from fruitfly_agent.runtime_spec import validate_execution
    def options(fields, bounds):
        if any(not field.startswith('parameters.') for field in fields):
            raise ValueError('execution grants must select parameters fields')
        return {'editable_fields': [field.removeprefix('parameters.') for field in fields],
                'bounds': {key.removeprefix('parameters.'): value for key, value in bounds.items()}}
    return ConfigurationSurface('execution-policy', 'H', 'configuration', 'execution', validate_execution,
                                edit_options=options)
