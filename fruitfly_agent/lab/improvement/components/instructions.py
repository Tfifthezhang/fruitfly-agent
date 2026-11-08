"""Reusable ownership of bounded role instructions, without sharing role behavior."""
from dataclasses import asdict
import json
from fruitfly_agent.improvement.contracts.optimization import OptimizationSpec, OptimizationField, TargetSnapshot, TargetBinding
from fruitfly_agent.improvement.contracts.versions import canonical_json


class InstructionTarget:
    structured_parameters = True
    optimization = OptimizationSpec('I', 'parameters', required_capabilities=frozenset({'improver-comparison'}), default_selected=False)
    required_capabilities = frozenset({'improver-comparison'})
    adoption_roles = frozenset({'I'})
    component_kind = 'improvement-instructions'

    def __init__(self, component_id, instructions, *, defaults, descriptions, label, text=None):
        self.component_id, self.instructions = component_id, instructions
        self.defaults, self.descriptions, self.label = defaults, descriptions, label
        self.text = text if text is not None else canonical_json({'instructions': asdict(instructions)})
        if self.parse(self.text) != instructions:
            raise ValueError('instruction source differs from installed role')

    def parse(self, text):
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError('duplicate instruction field: ' + key)
                result[key] = value
            return result
        value = json.loads(text, object_pairs_hook=unique)
        if not isinstance(value, dict) or set(value) != {'instructions'} or set(value['instructions']) != set(asdict(self.instructions)):
            raise ValueError('role candidate requires exactly its instruction fields')
        return type(self.instructions)(**value['instructions'])

    def snapshot(self):
        return TargetSnapshot(self.component_id, self.text, TargetBinding('artifact', self.component_id),
            'role-instructions-v1', 'I')

    def describe_fields(self, text=None):
        value = self.instructions if text is None else self.parse(text)
        return tuple(OptimizationField('parameters.instructions.' + key, 'string', self.descriptions[key], item,
            getattr(self.defaults, key), unit='characters', minimum=1, maximum=16000)
            for key, item in asdict(value).items())

    def validate(self, text):
        self.parse(text)

    def validate_options(self, options):
        allowed = {'parameters.instructions.' + key for key in asdict(self.instructions)}
        if not isinstance(options, dict) or set(options) - {'editable_fields', 'bounds'} or options.get('bounds'):
            raise ValueError('role grants accept instruction fields only')
        fields = options.get('editable_fields', sorted(allowed))
        if not isinstance(fields, list) or not fields or len(set(fields)) != len(fields) or set(fields) - allowed:
            raise ValueError('invalid role instruction grant')

    def validate_change(self, text, options):
        self.validate_options(options)
        value = self.parse(text)
        allowed = options.get('editable_fields', ['parameters.instructions.' + k for k in asdict(value)])
        for key, prior in asdict(self.instructions).items():
            if 'parameters.instructions.' + key not in allowed and getattr(value, key) != prior:
                raise ValueError('candidate changed a protected role instruction')

    def prepare_trial(self, config, text):
        raise ValueError('I publication requires an independent role comparison')
