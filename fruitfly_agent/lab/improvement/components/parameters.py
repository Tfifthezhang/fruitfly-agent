"""Owner-declared parameter candidates using the ordinary runtime assembler."""
from dataclasses import replace
import json
import math
from typing import Any

from fruitfly_agent.lab.algorithms.targets import TargetBinding, TargetSnapshot, TEXT_TARGET_PREFIX
from fruitfly_agent.improvement.contracts.versions import canonical_json


class ParameterTarget:
    component_kind = 'mechanism-parameters'
    required_capabilities = frozenset({'configuration-materialization'})

    def __init__(self, definition, parameters, fields):
        self.definition = definition
        self.values = definition.descriptor.normalize_parameters(parameters)
        self.editable = frozenset(fields)
        self.label = definition.descriptor.label + ' parameters'

    def snapshot(self):
        name = self.definition.descriptor.mechanism_id
        return TargetSnapshot(name, canonical_json(self.values),
            TargetBinding('configuration', 'component.' + name), 'mechanism-parameters-v1', self.definition.configuration_role)

    def parse(self, text):
        def unique(pairs):
            values = {}
            for name, value in pairs:
                if name in values:
                    raise ValueError('duplicate component parameter: ' + name)
                values[name] = value
            return values
        value = json.loads(text, object_pairs_hook=unique)
        if not isinstance(value, dict) or set(value) != set(self.values):
            raise ValueError('parameter candidate must preserve its complete registered shape')
        if self.definition.validate_parameters:
            self.definition.validate_parameters(value)
        return self.definition.descriptor.normalize_parameters(value)

    def validate(self, text):
        self.validate_change(text, {})

    def validate_options(self, options):
        if not isinstance(options, dict) or set(options) - {'editable_fields', 'bounds'}:
            raise ValueError('parameter grants need editable_fields/bounds')
        fields = options.get('editable_fields', sorted(self.editable))
        bounds = options.get('bounds', {})
        if (not isinstance(fields, list) or not fields or len(set(fields)) != len(fields)
                or set(fields) - self.editable or not isinstance(bounds, dict) or set(bounds) - set(fields)):
            raise ValueError('parameter grant includes a protected or unknown field')
        for name, limits in bounds.items():
            if (not isinstance(limits, dict) or not limits or set(limits) - {'minimum', 'maximum'}
                    or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in limits.values())
                    or isinstance(self.values[name], bool) or not isinstance(self.values[name], (int, float))
                    or limits.get('minimum', -math.inf) > limits.get('maximum', math.inf)):
                raise ValueError('parameter bounds must be finite ordered numeric limits')
        self.validate_change(self.snapshot().text, options)

    def validate_change(self, text, options):
        after = self.parse(text)
        editable = set(options.get('editable_fields', self.editable))
        if any(after[k] != v for k, v in self.values.items() if k not in editable):
            raise ValueError('candidate changed a fixed component parameter')
        for name, bounds in options.get('bounds', {}).items():
            if not bounds.get('minimum', -math.inf) <= after[name] <= bounds.get('maximum', math.inf):
                raise ValueError('component parameter exceeds experiment bounds: ' + name)

    def prepare_trial(self, config, text):
        if self.parse(text) != self.values:
            raise ValueError('parameter candidates require the shared configuration materializer')
        return config


def editable_parameters(definition, fields):
    """Declare, validate and install a parameter target for an existing owner."""
    from fruitfly_agent.lab.catalog.components import ComponentSpec
    name = definition.descriptor.mechanism_id
    fields = frozenset(fields)
    declared = {p.name for p in definition.descriptor.parameters}
    if not fields or fields - declared:
        raise ValueError('editable parameters must be declared by their owner')
    original_specs = definition.component_specs
    def specs(parameters, enabled):
        old = original_specs(parameters, enabled) if original_specs else ()
        return (*old, ComponentSpec(name, definition.configuration_role, 'mechanism-parameters',
            'mechanism-parameters-v1', ParameterTarget.required_capabilities)) if enabled else old
    def install(state, context, parameters):
        return definition.install(state, context, parameters).with_component(
            TEXT_TARGET_PREFIX + name, ParameterTarget(definition, parameters, fields))
    def options(selected, bounds):
        if any(not p.startswith('parameters.') for p in selected):
            raise ValueError('parameter grants must select parameters fields')
        value = {'editable_fields': [p.removeprefix('parameters.') for p in selected],
                 'bounds': {p.removeprefix('parameters.'): b for p, b in bounds.items()}}
        if set(value['editable_fields']) - fields:
            raise ValueError('parameter grant includes a protected or unknown field')
        return value
    def validate(component, options, inventory):
        if component != name:
            if definition.component_validator is None:
                raise ValueError('unknown parameter component')
            return definition.component_validator(component, options, inventory)
        values: dict[str, Any] = next((m['parameters'] for m in inventory.mechanisms if m['id'] == name), {})
        ParameterTarget(definition, values, fields).validate_options(options)
    return replace(definition, install=install, component_specs=specs,
        component_validator=validate, configuration_edit=options)
