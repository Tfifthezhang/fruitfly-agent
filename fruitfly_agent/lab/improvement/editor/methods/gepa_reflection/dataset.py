"""Convert the frozen reflection packet into GEPA examples within its batch."""
import json

from fruitfly_agent.improvement.contracts.versions import canonical_json, content_hash


def dataset(request, artifacts):
    packets = [item for item in request.context if item.path.rsplit('/', 1)[-1] == 'reflection-packet.json']
    if len(packets) != 1:
        raise ValueError('GEPA reflection requires one organized reflection packet')
    resource, = packets
    packet = json.loads(artifacts.read(resource.artifact_id))
    records = {record.run_id: record for record in request.records}
    tasks = {task.task_id: task for task in request.tasks}
    expected = [{'task_id': task.task_id, 'material_id': task.material_id,
                 'run_ids': [record.run_id for record in request.records if record.task_id == task.task_id]}
                for task in request.tasks]
    scope = packet['membership']
    actual = {row['task_id']: (row['material_id'], set(row['run_ids'])) for row in scope}
    if (len(actual) != len(scope)
            or actual != {row['task_id']: (row['material_id'], set(row['run_ids'])) for row in expected}
            or content_hash(canonical_json(scope)) != packet['scope_id']):
        raise ValueError('reflection packet scope differs from the proposal batch')
    cards = {card['task_id']: card for card in packet['cards']}
    if len(cards) != len(packet['cards']) or set(cards) != set(tasks):
        raise ValueError('reflection packet cards differ from the proposal batch')
    examples, supplied = [], {}
    findings = packet['group_findings']
    for task_id, task in tasks.items():
        card = cards[task_id]
        if not card['input'] or card['input']['artifact_id'] != content_hash(task.instruction):
            raise ValueError('reflection packet omits a task instruction')
        executions = card['executions']
        expected_runs = next(row['run_ids'] for row in expected if row['task_id'] == task_id)
        ids = [row['run_id'] for row in executions]
        if set(ids) != set(expected_runs) or len(ids) != len(expected_runs):
            raise ValueError('reflection packet omits or repeats task executions')
        if not executions:
            examples.append({'Inputs': {'task_id': task_id, 'instruction': task.instruction},
                             'Generated Outputs': None, 'Feedback': 'No retained execution'})
        for row in executions:
            record = records[row['run_id']]
            if row['output']['artifact_id'] != content_hash(record.output):
                raise ValueError('reflection packet output differs from the granted receipt')
            events = None
            if row['events']:
                event_id = row['events']['artifact_id']
                if not any(item.path == 'evidence/events.json' and item.artifact_id == event_id
                           for item in record.artifacts):
                    raise ValueError('reflection packet event index is outside its execution')
                source = json.loads(artifacts.read(event_id))
                events = [{name: event.get(name) for name in ('event_id', 'kind', 'tool_name', 'is_error')}
                          for event in source['events']]
            example = {'Inputs': {'task_id': task_id, 'instruction': task.instruction},
                       'Generated Outputs': {'run_id': record.run_id, 'status': record.status,
                                             'events': events, 'final_output': record.output},
                       'Feedback': {'declared_observations': row['observations'],
                                    'availability': row['observation_supply'],
                                    'organizer_findings': [item for item in findings
                                        if record.run_id in item['run_ids'] or record.run_id in item['control_ids']]}}
            examples.append(example)
            supplied[record.run_id] = canonical_json(example)
    return resource, examples, supplied
