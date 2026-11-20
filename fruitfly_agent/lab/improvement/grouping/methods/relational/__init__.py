"""Rank group neighbors over one frozen feature table."""
from fruitfly_agent.improvement.contracts.versions import canonical_json, content_hash


def select(tasks, features, *, method, position, size, seed):
    ordered = sorted(tasks, key=lambda task: (content_hash(canonical_json([seed, task])), task))
    if position >= len(ordered):
        raise ValueError('group position outside source pool')
    anchor = ordered[position]
    if size == 1:
        return [anchor]
    neighbors = [task for task in ordered if task != anchor]

    def similarity(left, right, field):
        lhs, rhs = set(features[left][field]), set(features[right][field])
        return len(lhs & rhs) / len(lhs | rhs) if lhs or rhs else 0

    if method in {'failure', 'text', 'trajectory'}:
        field = {'failure': 'outcomes', 'text': 'terms', 'trajectory': 'actions'}[method]
        neighbors.sort(key=lambda task: -similarity(anchor, task, field))
        return [anchor, *neighbors[:size - 1]]
    if method == 'matched':
        baseline = features[anchor]
        neighbors.sort(key=lambda task: (features[task]['outcomes'] != baseline['outcomes'],
                                         abs(features[task]['action_count'] - baseline['action_count']),
                                         abs(features[task]['attempts'] - baseline['attempts'])))
        return [anchor, *neighbors[:size - 1]]
    chosen = [anchor]
    while neighbors and len(chosen) < size:
        next_task = min(neighbors, key=lambda task: max(
            sum(similarity(task, member, field) for field in ('outcomes', 'terms', 'actions'))
            for member in chosen))
        chosen.append(next_task)
        neighbors.remove(next_task)
    return chosen
