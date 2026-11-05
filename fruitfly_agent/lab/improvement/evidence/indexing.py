"""Rebuildable navigation derived from immutable execution resources; no model."""
from dataclasses import asdict, replace

from fruitfly_agent.improvement.contracts.tasks import Resource
from fruitfly_agent.improvement.contracts.versions import canonical_json, content_hash
from fruitfly_agent.improvement.execution.facts import read_facts
from .decoding import decode_rows
from .events import extract_events, correlate_events
from .coverage import build_coverage

OVERVIEW_PATH = 'evidence/overview.json'
EVENTS_PATH = 'evidence/events.json'
COVERAGE_PATH = 'evidence/coverage.json'
SOURCES_PATH = 'evidence/sources.json'
DERIVED_PATHS = frozenset((OVERVIEW_PATH, EVENTS_PATH, COVERAGE_PATH, SOURCES_PATH))


def organize_evidence(task, record, artifacts):
    # Rebuild from originals: an existing overview alone does not establish freshness.
    originals = tuple(r for r in record.artifacts if r.path not in DERIVED_PATHS)
    record = replace(record, artifacts=originals)
    facts = read_facts(record, artifacts)
    sources, events = [], []
    for resource in originals:
        source = {'path': resource.path, 'artifact_id': resource.artifact_id, 'kind': resource.kind,
                  'status': 'retained'}
        sources.append(source)
        try:
            data = artifacts.read(resource.artifact_id)
            if resource.kind != 'trajectory' and not resource.path.endswith('/model-usage.json'):
                continue
            text = data.decode('utf-8')
            rows, source_format, gaps = decode_rows(text)
            source.update(format=source_format, gaps=gaps,
                          status='partial' if gaps and rows else 'unindexed' if gaps else 'indexed')
            events.extend(extract_events(resource, rows, source_format))
        except (ValueError, KeyError, OSError, UnicodeError, TypeError, AttributeError, IndexError) as exc:
            source.update(status='unindexed' if resource.kind == 'trajectory' else 'unavailable', reason=type(exc).__name__)
    correlate_events(events)
    identity = content_hash(canonical_json({'organizer': 'layered-evidence-2', 'run_id': record.run_id,
                                           'output': record.output, 'sources': sources}))
    coverage = build_coverage(record, sources, artifacts, facts)
    event_index = {'run_id': record.run_id, 'source_identity': identity, 'events': events,
                   'sources': sources, 'complete': coverage['evidence_complete'],
                   'execution_diagnostics_complete': coverage['execution_diagnostics_complete'],
                   'note': 'Events are source navigation. Derived views are not additional executions; use execution facts for counts.'}
    overview = {'run_id': record.run_id, 'task': task.instruction, 'status': record.status,
        'source_identity': identity, 'output_id': artifacts.put(record.output.encode()),
        'output_characters': len(record.output), 'output_excerpt': record.output[:2000],
        'termination_reason': facts.termination_reason if facts is not None else 'unknown',
        'elapsed_seconds': facts.elapsed_seconds if facts is not None else None,
        'usage': asdict(facts)['usage'] if facts is not None else [],
        'counters': dict(facts.counters) if facts is not None else {},
        'deliverables': [asdict(r) for r in originals if r.kind == 'deliverable'],
        'deliverable_scope': 'Captured file versions; consult the capture manifest for stage and final-state relationships.',
        'event_count': len(events), 'events_path': EVENTS_PATH, 'sources': sources,
        'coverage_path': COVERAGE_PATH, 'coverage': coverage,
        'complete': coverage['evidence_complete'],
        'execution_diagnostics_complete': coverage['execution_diagnostics_complete']}
    values = ((OVERVIEW_PATH, overview), (EVENTS_PATH, event_index),
              (COVERAGE_PATH, coverage), (SOURCES_PATH, {'sources': sources, 'source_identity': identity}))
    resources = tuple(Resource(path, artifacts.put(canonical_json(value).encode()), 'application/json', 'diagnostic')
                      for path, value in values)
    return replace(record, artifacts=(*originals, *resources))
