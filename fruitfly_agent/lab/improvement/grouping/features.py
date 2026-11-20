"""Extract deterministic task descriptions, outcome classes and action signatures."""
import re


def frozen_features(pool, read):
    features = {task.task_id: {'terms': sorted(set(re.findall(r'\w+', task.instruction.casefold()))),
                               'outcomes': set(), 'actions': set(), 'complete_indexes': 0,
                               'attempts': 0, 'action_count': 0, 'unavailable_indexes': 0}
                for task in pool.tasks}
    owners = {}
    for record in pool.records:
        owners[record.run_id] = record.task_id
        row = features[record.task_id]
        row['attempts'] += 1
        row['outcomes'].add('execution:' + record.status)
        resource = next((item for item in record.artifacts if item.path == 'evidence/events.json'), None)
        if resource is None:
            row['unavailable_indexes'] += 1
            continue
        try:
            document = read(resource)
        except (ValueError, KeyError, OSError):
            row['unavailable_indexes'] += 1
            continue
        if not isinstance(document, dict) or not isinstance(document.get('events'), list):
            row['unavailable_indexes'] += 1
            continue
        row['complete_indexes'] += int(document.get('complete') is True)
        actions = []
        for event in document['events']:
            kind = event['kind']
            if kind not in {'toolCall', 'toolResult'}:
                continue
            action = kind + ':' + (event.get('tool_name') or 'unknown')
            if event.get('is_error') is True:
                action += ':error'
            actions.append(action)
        row['actions'].update(actions)
        row['actions'].update(left + ' → ' + right for left, right in zip(actions, actions[1:]))
        row['action_count'] += len(actions)
    for observation in pool.observations:
        if not isinstance(observation, dict) or observation.get('run_id') not in owners:
            continue
        row = features[owners[observation['run_id']]]
        semantics = observation.get('semantics', {})
        if semantics.get('scope') == 'execution' and semantics.get('outcome') in {'met', 'unmet'}:
            row['outcomes'].add('outcome:' + semantics['outcome'])
        error = observation.get('exception_type')
        if isinstance(error, str) and error:
            row['outcomes'].add('error:' + error)
    return {task: {**row, 'outcomes': sorted(row['outcomes']), 'actions': sorted(row['actions'])}
            for task, row in features.items()}
