"""Declarative termination uses the existing pure policy implementations."""
from fruitfly_agent.lab.improvement.api import (AnyOf, AllOf, IterationLimit,
    NoImprovement, FailureLimit, ResourceLimit, ScoreAtLeast, MetricThreshold)

FACTORIES = {'iterations': IterationLimit, 'no_improvement': NoImprovement,
    'failures': FailureLimit, 'resource': ResourceLimit, 'score': ScoreAtLeast,
    'metric': MetricThreshold}


def stop_policy(value):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError('stop policy must be a mapping')
    for name, factory in (('any', AnyOf), ('all', AllOf)):
        if name in value:
            if set(value) != {name} or not isinstance(value[name], list) or not value[name]:
                raise ValueError('composite stopping needs a nonempty policy list')
            return factory(*(stop_policy(v) for v in value[name]))
    policy_type = value.get('type')
    if not isinstance(policy_type, str) or policy_type not in FACTORIES:
        raise ValueError('unknown stop policy')
    try:
        return FACTORIES[policy_type](**{k: v for k, v in value.items() if k != 'type'})
    except TypeError as exc:
        raise ValueError('invalid stop policy parameters') from exc
