"""Compact batch facts derived from granted records, without model judgments."""
from collections import Counter
import json
from fruitfly_agent.improvement.execution.facts import read_facts
from .summaries import execution_summary


def context_observations(context, artifacts):
    entries = [r for r in context if r.path == 'observations.json']
    if len(entries) > 1:
        raise ValueError('batch observations require one attributed resource')
    return tuple(json.loads(artifacts.read(entries[0].artifact_id))) if entries else ()


def batch_view(tasks, records, observations, artifacts):
    """Separate receipt status, observed values and unknown execution diagnostics."""
    by_run: dict[str, list[dict]] = {}
    for item in observations:
        if isinstance(item, dict) and item.get('run_id'):
            by_run.setdefault(item['run_id'], []).append(item)
    rows = []
    for receipt in records:
        prefix = 'context/executions/' + receipt.run_id
        facts = read_facts(receipt, artifacts)
        termination = next((r for r in receipt.artifacts if r.path == 'diagnostics/termination.json'), None)
        provenance = json.loads(artifacts.read(termination.artifact_id)) if termination else {}
        rows.append({**execution_summary(receipt, facts),
            'termination_source': provenance.get('source', 'unavailable'),
            'observations': by_run.get(receipt.run_id, []),
            'observation_supply': 'available' if receipt.run_id in by_run else 'not_supplied',
            'metadata': prefix + '/metadata.json',
            'overview': prefix + '/evidence/overview.json' if any(r.path == 'evidence/overview.json' for r in receipt.artifacts) else None})
    return {'overview.json': {'task_count': len(tasks), 'execution_count': len(records),
        'execution_status_counts': dict(Counter(r.status for r in records)),
        'observation_name_counts': dict(Counter(o.get('name', 'unknown') for o in observations if isinstance(o, dict))),
        'scope': 'Deterministic facts over supplied records; no original-reading or quality claim.'},
        'executions.json': rows,
        'coverage.json': {'directory_complete': True, 'execution_count': len(rows),
            'executions_with_observations': sum(bool(r['observations']) for r in rows),
            'executions_with_terminal_source': sum(r['termination_source'] == 'native_terminal_diagnostics' for r in rows),
            'original_reading': 'not_established',
            'scope': 'Unavailable observations were not supplied; absence is not inferred.'}}
