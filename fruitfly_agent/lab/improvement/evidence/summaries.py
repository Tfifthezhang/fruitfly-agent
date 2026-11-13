"""Small execution facts for consumers that select which evidence to investigate.

This projection performs no ranking, diagnosis, task selection or backend access.
"""
from dataclasses import asdict


def execution_summary(record, facts):
    """Preserve accounting scopes and unknowns without copying evidence catalogs."""
    return {
        'run_id': record.run_id,
        'task_id': record.task_id,
        'harness_id': record.harness_id,
        'material_id': record.material_id,
        'conditions_id': record.conditions_id,
        'initial_state_id': record.initial_state_id,
        'status': record.status,
        'termination_reason': facts.termination_reason if facts else 'unknown',
        'elapsed_seconds': facts.elapsed_seconds if facts else None,
        'model_calls': record.model_calls,
        'usage': [asdict(value) for value in facts.usage] if facts else [],
        'counters': dict(facts.counters) if facts else {},
        'diagnostics_complete': facts.complete if facts else None,
        'diagnosable': facts.diagnosable if facts else None,
        'output_id': facts.output_id if facts else None,
        'output_characters': len(record.output),
        'evidence_count': len(record.artifacts),
    }
