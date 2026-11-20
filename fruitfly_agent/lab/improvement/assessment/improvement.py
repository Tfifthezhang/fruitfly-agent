"""Apply authorized objective thresholds to an independent frozen pair."""
import json

from fruitfly_agent.improvement.contracts.optimization import (
    OptimizationField, OptimizationSpec, TargetBinding, TargetSnapshot,
)
from fruitfly_agent.improvement.contracts.versions import canonical_json

POLICY_FIELDS = {'minimum_gain': (0, 1_000_000), 'maximum_regression_rate': (0, 1)}
_PREFIX = 'parameters.settings.'


class ComparisonTarget:
    structured_parameters = True
    component_kind = 'improvement-policy'
    label = 'Measured comparison thresholds'
    required_capabilities = frozenset({'improver-comparison'})
    optimization = OptimizationSpec('I', 'parameters', required_capabilities=required_capabilities,
                                    default_selected=False)

    def __init__(self, parameters=None):
        from .registration import normalize
        self.parameters = normalize(parameters or {})

    def parse(self, text):
        from .registration import normalize
        values = json.loads(text)
        if (not isinstance(values, dict) or set(values) != {'settings'}
                or not isinstance(values['settings'], dict)
                or set(values['settings']) != set(self.parameters['settings'])):
            raise ValueError('candidate must preserve the comparison policy fields')
        return normalize(values)

    def snapshot(self):
        return TargetSnapshot('improvement-comparison', canonical_json(self.parameters),
                              TargetBinding('artifact', 'improvement-comparison'), 'comparison-settings-v1', 'I')

    def describe_fields(self, text=None):
        values = self.parameters if text is None else self.parse(text)
        return tuple(OptimizationField(_PREFIX + key, 'number', key.replace('_', ' '),
                                      values['settings'][key], None, minimum=lo, maximum=hi)
                     for key, (lo, hi) in POLICY_FIELDS.items())

    def validate_options(self, options):
        allowed = {_PREFIX + key for key in POLICY_FIELDS}
        if not isinstance(options, dict) or set(options) - {'editable_fields'}:
            raise ValueError('comparison grants accept threshold fields only')
        fields = options.get('editable_fields', sorted(allowed))
        if not isinstance(fields, list) or not fields or len(fields) != len(set(fields)) or set(fields) - allowed:
            raise ValueError('comparison grants accept threshold fields only')

    def validate(self, text):
        self.parse(text)

    def validate_change(self, text, options):
        self.validate_options(options)
        before, after = self.parameters['settings'], self.parse(text)['settings']
        selected = options.get('editable_fields', [_PREFIX + key for key in POLICY_FIELDS])
        if before['method'] != 'measured' or after['method'] != before['method']:
            raise ValueError('threshold candidates require the unchanged measured method')
        if any(before[key] != after[key] and _PREFIX + key not in selected for key in POLICY_FIELDS):
            raise ValueError('candidate changed a protected comparison threshold')

    def prepare_trial(self, config, text):
        raise ValueError('comparison thresholds require an independent frozen-pair trial')


def candidate_comparison(before, after, manifest, input_ids, baseline, document, *, options):
    from ..components.text import TextComponentAdapter
    from .methods.measured import compare_measured
    from .registration import apply_thresholds

    target = ComparisonTarget(baseline)
    adapter = TextComponentAdapter(target, target.component_kind)
    adapter.validate(document)
    text = adapter.to_text(document)
    target.validate_change(text, options)
    policy = apply_thresholds(target.parse(text), manifest)
    return compare_measured(before, after, policy, input_ids)
