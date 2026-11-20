"""Run one small, event-attributed extraction inside the fixed group."""
import hashlib
import json
from collections import defaultdict

from fruitfly_agent.improvement.contracts.versions import canonical_json
from ....evidence.access import EvidenceAccess
from ....evidence.resources import ReferenceWorkspace


class UnitWorkspace(ReferenceWorkspace):
    """Resolve only the event body or exact source interval granted to this unit."""

    def __init__(self, *, parent, spans, **kwargs):
        super().__init__(**kwargs)
        self.parent, self.spans = parent, spans

    def paths(self):
        return tuple(sorted((*super().paths(), *self.spans)))

    def read(self, path):
        span = self.spans.get(path)
        if span is None:
            return super().read(path)
        source, identity, start, end = span
        data = self.parent.read(source)
        if 'sha256:' + hashlib.sha256(data).hexdigest() != identity:
            raise ValueError('extraction source identity mismatch')
        if start is None:
            return data
        text = data.decode('utf-8')
        if not 0 <= start < end <= len(text):
            raise ValueError('invalid extraction source interval')
        return text[start:end].encode()


async def extract(session, mission, system, unit, workspace, task_input, services, *, model_request_ceiling=None):
    index_path = unit['event_index']['path']
    index_bytes = workspace.read(index_path)
    if 'sha256:' + hashlib.sha256(index_bytes).hexdigest() != unit['event_index']['artifact_id']:
        raise ValueError('extraction event index identity mismatch')
    index = json.loads(index_bytes)
    by_id = {event['event_id']: event for event in index['events']}
    fields = ('event_id', 'kind', 'tool_name', 'is_error', 'status', 'call_event_id', 'timestamp')
    prefix = index_path.removesuffix('evidence/events.json')
    granted = set(workspace.paths())
    unit_ids = set(unit['event_ids'])
    outside_intervals = defaultdict(list)
    for event_id, event in by_id.items():
        if event_id not in unit_ids and {'source_path', 'start', 'end'} <= event.keys():
            outside_intervals[event['source_path']].append((event['start'], event['end']))
    evidence, spans = [], {}
    for position, event_id in enumerate(unit['event_ids']):
        event = by_id[event_id]
        row = {key: event.get(key) for key in fields}
        row['source'] = None
        row['source_status'] = 'unavailable'
        if index_path.endswith('evidence/events.json'):
            body = 'body_path' in event
            source = prefix + event.get('body_path' if body else 'source_path', '')
            shared_span = not body and 'start' in event and any(
                start < event['end'] and event['start'] < end
                for start, end in outside_intervals[event.get('source_path')])
            if shared_span:
                row['source_status'] = 'shared_with_other_unit'
            if source in granted and not shared_span:
                identity = event['body_artifact_id' if body else 'artifact_id']
                start, end = (None, None) if body else (event['start'], event['end'])
                path = f'context/unit-events/{position}.txt'
                spans[path] = source, identity, start, end
                row['source'] = {'path': path, 'artifact_id': identity, 'start': start, 'end': end}
                row['source_status'] = 'granted'
        evidence.append(row)
    local = UnitWorkspace(
        parent=workspace, spans=spans,
        artifacts=workspace.artifacts, baseline=workspace.baseline, writable_ids=(),
        references={'context/task.md': task_input['artifact_id']},
        files={'context/unit.json': canonical_json({'events': evidence,
            'previous_event': unit['previous_event']}).encode()},
        access=EvidenceAccess((unit['run_id'],), record=services.record, budget=workspace.access.budget),
        record=services.record, max_bytes=workspace.max_bytes,
    )
    response = await session.session(mission, local, services, system=system,
        model_request_ceiling=model_request_ceiling,
        initial_content=canonical_json({'task_id': unit['task_id'], 'run_id': unit['run_id'],
                                        'contract': 'context/task.md', 'events': 'context/unit.json'}))
    observations = json.loads(response)
    if not isinstance(observations, list) or len(observations) > len(evidence):
        raise ValueError('local observations must be a bounded list')
    for observation in observations:
        if (not isinstance(observation, dict) or set(observation) != {'event_id', 'observation'}
                or not isinstance(observation['event_id'], str) or observation['event_id'] not in unit['event_ids']
                or not isinstance(observation['observation'], str)
                or not 1 <= len(observation['observation'].strip()) <= 500):
            raise ValueError('invalid local observation or event grant')
    return observations
