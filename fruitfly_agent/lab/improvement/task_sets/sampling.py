"""Deterministic collection-stratified cycles over a frozen development set."""
import random
from fruitfly_agent.improvement.contracts.evaluation import EvaluationBatch


def sample_batch(snapshot, settings, round_index, *, attempts=1):
    entries = snapshot.partition('development')
    keys = {e.key for e in entries}
    if settings.policy == 'all':
        chosen = tuple(e.key for e in entries)
    elif settings.policy == 'fixed':
        if set(settings.task_keys) - keys:
            raise ValueError('fixed sampling cites unavailable development tasks')
        chosen = settings.task_keys
    else:
        groups: dict[str, list[str]] = {}
        for entry in entries:
            groups.setdefault(entry.collection_id, []).append(entry.key)
        size = min(settings.batch_size, len(entries))
        if size < len(groups):
            raise ValueError('batch_size must cover every development collection')
        ordered = sorted(groups)
        generator = random.Random(settings.seed)
        for group in ordered:
            generator.shuffle(groups[group])
        # Fixed per-collection quotas guarantee coverage across consecutive rounds.
        quotas = {group: 0 for group in ordered}
        for _ in range(size):
            group = min((g for g in ordered if quotas[g] < len(groups[g])), key=lambda g: (quotas[g], g))
            quotas[group] += 1
        chosen = tuple(groups[g][(round_index * quotas[g] + i) % len(groups[g])]
            for g in ordered for i in range(quotas[g]))
    return EvaluationBatch(snapshot.snapshot_id, chosen, attempts=attempts)
