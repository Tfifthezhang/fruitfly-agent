"""Project public results without pretending a task set is a single deliverable."""
import json
from fruitfly_agent.lab.improvement.api import TaskSetSnapshot, TaskSetOutcome


def material_details(material):
    if isinstance(material, TaskSetSnapshot):
        return (('Task set', material.snapshot_id), ('Tasks', str(len(material.entries))))
    return (('Task', material.instruction), ('Input files', ', '.join(r.path for r in material.inputs) or '(none)'))


def result_view(outcome):
    if outcome is None:
        return {'label': 'Official execution', 'id': '', 'output': '', 'assurance': 'unavailable', 'exploration': '', 'evidence': ()}
    if isinstance(outcome, TaskSetOutcome):
        selected = outcome.selected
        return {'label': 'Official evaluation', 'id': selected.evaluation_id if selected else '',
            'output': json.dumps({'task_set_id': outcome.task_set.snapshot_id,
                'score': selected.assessment.score if selected else None,
                'collections': dict(selected.assessment.collections) if selected else {},
                'expected': selected.assessment.expected if selected else 0,
                'completed': selected.assessment.completed if selected else 0}),
            'assurance': outcome.decision.assurance if outcome.decision else 'unavailable',
            'exploration': outcome.exploration[-1]['evaluation_id'] if outcome.exploration else '',
            'evidence': (('Joint development score', str(selected.assessment.score)),
                ('Selection coverage', f'{selected.assessment.completed}/{selected.assessment.expected}'),
                ('Collection scores', json.dumps(dict(selected.assessment.collections)))) if selected else ()}
    return {'label': 'Official execution', 'id': outcome.selected.run_id if outcome.selected else '',
        'output': outcome.selected.output if outcome.selected else '',
        'assurance': outcome.decision.assurance if outcome.decision else 'unavailable',
        'exploration': outcome.exploration[-1].run_id if outcome.exploration else '', 'evidence': ()}
