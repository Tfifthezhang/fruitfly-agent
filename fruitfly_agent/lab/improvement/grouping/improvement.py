"""Grant bounded group-size changes and run the same frozen composition."""
import json

from fruitfly_agent.improvement.contracts.optimization import (
    OptimizationField, OptimizationSpec, TargetBinding, TargetSnapshot,
)
from fruitfly_agent.improvement.contracts.versions import canonical_json

_COMPONENT = 'improvement-grouping'
_FIELD = 'parameters.settings.batch_size'
_SCHEMA = 'group-settings-v1'
MAX_BATCH_SIZE = 100_000


class GroupingTarget:
    structured_parameters = True
    component_kind = 'improvement-policy'
    label = 'Feedback group composition'
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
            raise ValueError('candidate must preserve all grouping settings')
        return normalize(values)

    def snapshot(self):
        return TargetSnapshot(_COMPONENT, canonical_json(self.parameters),
                              TargetBinding('artifact', _COMPONENT), _SCHEMA, 'I')

    def describe_fields(self, text=None):
        settings = self.parameters if text is None else self.parse(text)
        return (OptimizationField(_FIELD, 'integer', 'Maximum number of tasks per group',
                                  settings['settings']['batch_size'], GroupingTarget().parameters['settings']['batch_size'],
                                  minimum=1, maximum=MAX_BATCH_SIZE),)

    def validate_options(self, options):
        if (not isinstance(options, dict) or set(options) - {'editable_fields'}
                or options.get('editable_fields', [_FIELD]) != [_FIELD]):
            raise ValueError('grouping grants select the bounded batch size')

    def validate(self, text):
        self.parse(text)

    def validate_change(self, text, options):
        self.validate_options(options)
        authored = self.parse(text)['settings']
        prior = self.parameters['settings']
        if any(authored[key] != prior[key] for key in ('method', 'seed')):
            raise ValueError('candidate changed protected grouping fields')

    def prepare_trial(self, config, text):
        raise ValueError('grouping requires an independent frozen-pool comparison')


def candidate_group(pool, source, baseline, document, *, options, position, members=None, features=None):
    from ..components.text import TextComponentAdapter
    from .publication import compose

    target = GroupingTarget(baseline)
    adapter = TextComponentAdapter(target, target.component_kind)
    adapter.validate(document)
    text = adapter.to_text(document)
    target.validate_change(text, options)
    return compose(pool, source, target.parse(text)['settings'], position, members, features=features)
