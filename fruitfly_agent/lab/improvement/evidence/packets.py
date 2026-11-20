"""Build a backend-neutral packet over a single granted organization scope."""
import json

from fruitfly_agent.improvement.contracts.versions import canonical_json, content_hash


def reflection_packet(request, workspace, batch, guide):
    """Record every task and exact retrieval anchors for available material."""
    references = workspace.references
    runs = {row['run_id']: row for row in json.loads(workspace.read('context/executions.json'))}
    cards = []
    detailed = {item['task_id']: item for item in batch['tasks']}
    for task in request.tasks:
        item = detailed.get(task.task_id)
        if item is None:
            cards.append({'task_id': task.task_id, 'input': None, 'executions': [],
                          'retention_status': 'no_detailed_execution'})
            continue
        executions = []
        for row in item['executions']:
            run_id = row['run_id']
            event_path = 'context/executions/' + run_id + '/evidence/events.json'
            facts = runs[run_id]
            executions.append({
                'run_id': run_id,
                'status': row['status'],
                'output': _reference(row['output'], references),
                'events': _reference(event_path, references),
                'sources': _reference(row['sources'], references),
                'observations': facts['observations'],
                'observation_supply': facts['observation_supply'],
            })
        cards.append({'task_id': item['task_id'], 'input': _reference(item['task'], references),
                      'executions': executions,
                      'retention_status': 'available' if executions else 'no_detailed_execution'})
    members = [{'task_id': task.task_id, 'material_id': task.material_id,
                'run_ids': [record.run_id for record in request.records if record.task_id == task.task_id]}
               for task in request.tasks]
    return {'scope_id': content_hash(canonical_json(members)), 'membership': members, 'cards': cards,
            'parent_applicability': 'unverified', 'group_findings': guide['findings'],
            'coverage': {'tasks': len(members), 'cards': len(cards),
                         'cards_with_executions': sum(bool(card['executions']) for card in cards),
                         'chronology': 'retrieve_granted_event_indexes'}}


def _reference(path, references):
    identity = references.get(path)
    return {'path': path, 'artifact_id': identity} if identity else None
