"""Generate deterministic task-local units from granted event indexes."""
import json

from fruitfly_agent.improvement.contracts.versions import canonical_json, content_hash


def schedule(packet, workspace, events_per_unit):
    if type(events_per_unit) is not int or events_per_unit < 1:
        raise ValueError('events_per_unit must be positive')
    units = []
    for card in packet['cards']:
        if not card['executions']:
            units.append(_unit(card['task_id'], None, None, (), None, 'missing_execution'))
            continue
        for execution in card['executions']:
            index = execution['events']
            if index is None:
                units.append(_unit(card['task_id'], execution['run_id'], None, (), None, 'missing_index'))
                continue
            document = json.loads(workspace.read(index['path']))
            event_ids = tuple(event['event_id'] for event in document['events'])
            if not event_ids:
                units.append(_unit(card['task_id'], execution['run_id'], index, (), None, 'empty_index'))
            for start in range(0, len(event_ids), events_per_unit):
                units.append(_unit(card['task_id'], execution['run_id'], index,
                                   event_ids[start:start + events_per_unit],
                                   event_ids[start - 1] if start else None, 'pending'))
    return units


def _unit(task_id, run_id, index, event_ids, previous_event, state):
    fields = {'task_id': task_id, 'run_id': run_id, 'event_index': index,
              'event_ids': event_ids, 'previous_event': previous_event, 'state': state}
    return {'unit_id': content_hash(canonical_json(fields)), **fields}
