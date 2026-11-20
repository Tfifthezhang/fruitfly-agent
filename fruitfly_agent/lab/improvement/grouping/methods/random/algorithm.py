"""Seeded partition ordered by hashes so membership is portable."""
from fruitfly_agent.improvement.contracts.versions import canonical_json, content_hash


def select(task_ids, members, position, batch_size, seed):
    if members is not None:
        raise ValueError('random grouping takes no authored members')
    ordered = sorted(task_ids, key=lambda task: (content_hash(canonical_json([seed, task])), task))
    start = position * batch_size
    if start >= len(ordered):
        raise ValueError('group position outside source pool')
    return ordered[start:start + batch_size]
