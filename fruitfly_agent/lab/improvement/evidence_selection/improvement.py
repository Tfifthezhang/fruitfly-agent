"""Owner grants and isolated execution for evidence-selection I candidates."""
from dataclasses import asdict
import json
from fruitfly_agent.improvement.contracts.optimization import OptimizationSpec, OptimizationField, TargetSnapshot, TargetBinding
from fruitfly_agent.improvement.contracts.versions import canonical_json
from .configuration import SelectionSettings, LIMITS
from .methods.representative.algorithm import RepresentativeSelector


class SelectionTarget:
    structured_parameters = True
    component_kind = 'improvement-policy'
    label = 'Improvement evidence selection'
    required_capabilities = frozenset({'improver-comparison'})
    optimization = OptimizationSpec('I', 'parameters', required_capabilities=required_capabilities, default_selected=False)

    def __init__(self, settings=None):
        self.settings = settings or SelectionSettings()

    def snapshot(self):
        return TargetSnapshot('improvement-evidence-selection',
            canonical_json({'settings': asdict(self.settings)}),
            TargetBinding('artifact', 'improvement-evidence-selection'), 'evidence-selection-v1', 'I')

    def parse(self, text):
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError('duplicate evidence selection field')
                result[key] = value
            return result
        values = json.loads(text, object_pairs_hook=unique)
        if not isinstance(values, dict) or set(values) != {'settings'} or set(values['settings']) != set(asdict(self.settings)):
            raise ValueError('candidate must preserve complete selection settings')
        return SelectionSettings.from_parameters(values)

    def describe_fields(self, text=None):
        values = asdict(self.settings if text is None else self.parse(text))
        defaults = asdict(SelectionSettings())
        return tuple(OptimizationField('parameters.settings.' + key, 'integer' if key in LIMITS else 'string',
            {'max_cases': 'Maximum detailed execution cases.', 'controls': 'Reserved successful controls.',
             'max_per_task': 'Maximum detailed cases for one task.', 'slow_seconds': 'Elapsed-time investigation threshold.',
             'many_calls': 'Model-call investigation threshold.', 'many_tools': 'Execution tool-start investigation threshold.',
             'high_tokens': 'Per-resource execution token investigation threshold.',
             'material_policy': 'Focused evidence or every retained granted material.'}[key], value, defaults[key],
            minimum=LIMITS[key][0] if key in LIMITS else None,
            maximum=LIMITS[key][1] if key in LIMITS else None,
            choices=() if key in LIMITS else ('focused', 'all-granted')) for key, value in values.items())

    def validate_options(self, options):
        fields = {'parameters.settings.' + k for k in asdict(self.settings)}
        if not isinstance(options, dict) or set(options) - {'editable_fields', 'bounds'}:
            raise ValueError('invalid evidence selection grant')
        selected = options.get('editable_fields', sorted(fields))
        bounds = options.get('bounds', {})
        if (not isinstance(selected, list) or not selected or len(selected) != len(set(selected))
                or set(selected) - fields or not isinstance(bounds, dict) or set(bounds) - set(selected)):
            raise ValueError('invalid evidence selection fields')
        for path, limits in bounds.items():
            if path.removeprefix('parameters.settings.') not in LIMITS:
                raise ValueError('numeric bounds cannot constrain material policy')
            low, high = LIMITS[path.removeprefix('parameters.settings.')]
            if (not isinstance(limits, dict) or not limits or set(limits) - {'minimum', 'maximum'}
                    or any(type(v) is not int for v in limits.values())
                    or not low <= limits.get('minimum', low) <= limits.get('maximum', high) <= high):
                raise ValueError('invalid evidence selection bounds')

    def validate(self, text):
        self.parse(text)

    def validate_change(self, text, options):
        self.validate_options(options)
        values, prior = asdict(self.parse(text)), asdict(self.settings)
        selected = options.get('editable_fields', ['parameters.settings.' + k for k in prior])
        for key, value in values.items():
            path = 'parameters.settings.' + key
            if path not in selected and value != prior[key]:
                raise ValueError('candidate changed protected selection setting')
            limits = options.get('bounds', {}).get(path, {})
            if key in LIMITS and not limits.get('minimum', LIMITS[key][0]) <= value <= limits.get('maximum', LIMITS[key][1]):
                raise ValueError('selection candidate exceeds granted bounds')

    def prepare_trial(self, config, text):
        raise ValueError('evidence selection I requires independent research comparison')


def candidate_selector(document, *, options, baseline=None):
    from ..components.text import TextComponentAdapter
    target = SelectionTarget(baseline)
    adapter = TextComponentAdapter(target, target.component_kind)
    adapter.validate(document)
    text = adapter.to_text(document)
    target.validate_change(text, options)
    return RepresentativeSelector(target.parse(text))
