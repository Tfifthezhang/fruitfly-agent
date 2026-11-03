"""Offline allowance-capacity analysis, never a prediction or a timeout override."""
from __future__ import annotations

import math
from typing import Any


def execution_budget(tasks: list[dict[str, Any]], attempts: int, concurrency: int, timeout: float) -> dict[str, Any]:
    allowances = [task.get('configuration', {}).get('agent', {}).get('timeout_sec') for task in tasks]
    known = [float(value) for value in allowances if type(value) in (int, float) and math.isfinite(value) and value > 0]
    total = sum(known) * attempts
    capacity = max(total / concurrency, max(known, default=0.))
    return {'job_timeout_seconds': timeout, 'concurrency': concurrency,
        'tasks_with_agent_allowance': len(known), 'tasks_without_agent_allowance': len(tasks) - len(known),
        'agent_allowance_seconds': total, 'agent_allowance_per_worker_seconds': total / concurrency,
        'minimum_capacity_for_declared_allowances_seconds': capacity,
        'shorter_than_agent_allowances': timeout < capacity,
        'note': 'Allowance capacity, not predicted runtime; setup, verifier, cleanup and scheduling imbalance are additional.'}
