"""One evidence-grounded candidate per round; composition is optional elsewhere."""
from .registry import SearchSchedule, StrategyDefinition


def schedule(plan):
    if plan.width != 1:
        raise ValueError('simple search supports one candidate per round; use depth for rounds')
    return SearchSchedule(1, plan.depth, (('propose', 0),))


def definition():
    return StrategyDefinition('simple', 'simple-v1', 'One candidate at a time', schedule, validate_options)


def validate_options(options):
    if options.width != 1 or options.mode != 'parallel':
        raise ValueError('simple uses rounds, without width or mode overrides')
