"""Algorithm-specific scopes, reference width and composition count."""
from ..registry import SearchSchedule, StrategyDefinition


def schedule(plan):
    width = plan.width if plan.mode == 'parallel' else 1
    return SearchSchedule(plan.width, plan.depth if plan.mode == 'sequential' else 1,
        tuple((scope, index) for index in range(width) for scope in ('invariant', 'domain')), width)


def definition():
    return StrategyDefinition('harness2', 'propose-probe-compose-v3', 'Harness²', schedule)
