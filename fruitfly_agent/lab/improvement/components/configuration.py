"""Executable I setting targets, with fixed outer budgets and comparison rules."""
import json

from fruitfly_agent.lab.algorithms.targets import TargetBinding, TargetSnapshot
from ..contracts.versions import canonical_json
from ..system_configuration import feedback_parameters, search_parameters


def flatten(value, prefix=''):
    result = {}
    for name, item in value.items():
        key = prefix + name
        if isinstance(item, dict):
            result.update(flatten(item, key + '.'))
        else:
            result[key] = item
    return result


class ImprovementSettingsTarget:
    component_kind = 'improvement-settings'
    required_capabilities = frozenset({'improver-comparison'})
    adoption_roles = frozenset({'I'})

    def __init__(self, key, parameters):
        self.key = key
        self.label = 'Improvement ' + key
        definitions = {
            'feedback': (feedback_parameters, {'evidence.page_characters', 'judgment_guidance', 'comparison_guidance',
                                              'process_assessment.assessors'}),
            'search': (search_parameters, {'strategy', 'rounds', 'exploration'})}
        self.normalize, self.editable = definitions[key]
        self.parameters = self.normalize(parameters)

    def snapshot(self):
        key = 'improvement-' + self.key
        return TargetSnapshot(key, canonical_json(self.parameters), TargetBinding('artifact', key),
                              'improvement-settings-v1', 'I')

    def parse(self, text):
        from fruitfly_agent.runtime_spec.documents import UniqueLoader
        import yaml
        value = yaml.load(text, Loader=UniqueLoader)
        # Publication uses JSON; YAML is not an additional editor output protocol.
        if json.loads(text) != value:
            raise ValueError('settings candidate must contain a JSON object')
        return self.normalize(value)

    def validate(self, text):
        self.validate_change(text, {})

    def validate_options(self, options):
        if not isinstance(options, dict) or set(options) - {'editable_fields', 'bounds'}:
            raise ValueError('I settings options need editable_fields/bounds')
        editable = options.get('editable_fields', sorted(self.editable))
        if (not isinstance(editable, list) or not editable or len(set(editable)) != len(editable)
                or set(editable) - self.editable or set(options.get('bounds', {})) - set(editable)):
            raise ValueError('I settings grant includes fixed or unknown fields')
        for bounds in options.get('bounds', {}).values():
            if (not isinstance(bounds, dict) or not bounds or set(bounds) - {'minimum', 'maximum'}
                    or any(type(v) is not int for v in bounds.values())
                    or bounds.get('minimum', 0) > bounds.get('maximum', float('inf'))):
                raise ValueError('I settings bounds require ordered integer values')
        self.validate_change(self.snapshot().text, options)

    def validate_change(self, text, options):
        before, after = flatten(self.parameters), flatten(self.parse(text))
        if set(before) != set(after):
            raise ValueError('candidate changed the registered I settings shape')
        editable = set(options.get('editable_fields', self.editable))
        if any(after[key] != value for key, value in before.items() if key not in editable):
            raise ValueError('candidate changed a fixed I setting')
        for key, bounds in options.get('bounds', {}).items():
            if type(after[key]) is not int or not bounds.get('minimum', -float('inf')) <= after[key] <= bounds.get('maximum', float('inf')):
                raise ValueError('candidate I setting exceeds experiment bounds: ' + key)

    def prepare_trial(self, config, text):
        raise ValueError('I settings require a fixed-I comparison runner')
