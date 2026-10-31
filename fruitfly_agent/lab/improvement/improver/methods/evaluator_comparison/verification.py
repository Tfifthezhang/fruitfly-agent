"""Run the fixed outer reference policy, never a candidate evaluator judgment."""
from inspect import isawaitable


def reference_policy(episode):
    policy = episode.suite.evaluation_policy
    if not callable(getattr(policy, 'score', None)):
        raise ValueError('I comparison requires an independent reference policy')
    return policy


async def measure(policy, output, case, services):
    result = policy.score(output, case)
    if isawaitable(result):
        result = await services.operation(result, stage='evaluator')
    return result.score
