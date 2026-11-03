"""One Session codec and reader for operation evidence consumed by all hosts."""
from __future__ import annotations

from collections import defaultdict
import json
import logging
from pathlib import Path
from typing import Any, Iterable

from ..observation import ObservationSink, OperationEvent
from .protocol import SessionLike

logger = logging.getLogger(__name__)


def session_observer(session: SessionLike | None, observer: ObservationSink | None = None) -> ObservationSink:
    def emit(event: OperationEvent) -> None:
        if session is not None:
            try:
                session.append('meta', {'kind': 'operation', 'schema_version': 1, 'data': event.to_dict()})
            except Exception:
                # A poisoned Session is checked by Core before the next request.
                logger.warning('operation persistence failed', exc_info=True)
        if observer is not None:
            observer(event)
    return emit


def read_observations(path: Path, *, allow_incomplete: bool = False) -> list[OperationEvent]:
    result = []
    with path.open(encoding='utf-8') as source:
        for line in source:
            try:
                row = json.loads(line)
            except ValueError:
                if allow_incomplete and not line.endswith('\n'):
                    break  # A torn final write is not a completed event.
                raise
            if not isinstance(row, dict):
                raise ValueError('Session entry must be an object')
            if row.get('type') != 'meta' or row.get('kind') != 'operation':
                continue
            if row.get('schema_version') != 1:
                raise ValueError('unsupported operation record schema')
            result.append(OperationEvent.from_dict(row['data']))
    return result


def read_observation_files(paths: Iterable[Path], *, allow_incomplete: bool = False) -> list[OperationEvent]:
    """Combine declared evidence files without assigning meaning to their paths."""
    return [event for path in paths for event in read_observations(path, allow_incomplete=allow_incomplete)]


def summarize_observations(events: Iterable[OperationEvent]) -> dict[str, Any]:
    started: dict[str, OperationEvent] = {}
    finished: dict[str, OperationEvent] = {}
    stages: dict[str, dict[str, Any]] = {}
    intervals: dict[str, list[tuple[float, float]]] = defaultdict(list)
    failures = []
    for event in events:
        if event.state == 'started':
            started[event.operation_id] = event
            continue
        if event.operation_id in finished:
            raise ValueError('duplicate operation completion')
        finished[event.operation_id] = event
        seconds = event.elapsed_seconds or 0.
        aggregate = stages.setdefault(event.stage, {'count': 0, 'operation_seconds': 0., 'failed': 0, 'cancelled': 0})
        aggregate['count'] += 1
        aggregate['operation_seconds'] += seconds
        aggregate['failed'] += int(event.state in {'failed', 'cleanup_unconfirmed'})
        aggregate['cancelled'] += int(event.state == 'cancelled')
        intervals[event.clock_id].append((event.started_monotonic, event.started_monotonic + seconds))
        if event.failure is not None:
            failures.append(event.failure.to_dict())
    wall = 0.
    for values in intervals.values():
        end = 0.
        for left, right in sorted(values):
            wall += max(0., right - max(left, end))
            end = max(end, right)
    return {'observed': bool(started or finished), 'stages': stages,
        'observed_wall_seconds': wall,
        'unfinished': [event.to_dict() for key, event in started.items() if key not in finished],
        'failures': failures[-32:],
        'note': 'Stage totals overlap. Wall time is the union of completed intervals per process clock; unfinished durations are unknown.'}
