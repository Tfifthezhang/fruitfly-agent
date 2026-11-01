"""Cross-round navigation links existing records without repeating their facts."""
import json
from fruitfly_agent.improvement.contracts.lifecycle import ContextContribution
from fruitfly_agent.improvement.contracts.tasks import Resource
from fruitfly_agent.improvement.contracts.versions import canonical_json


def round_navigation(services, run_ids=None):
    allowed = None if run_ids is None else set(run_ids)
    rows = []
    for name, data in getattr(services, 'events', ()):
        # Nested studies own their evidence grants; an outer index cannot widen them.
        if 'episode_id' in data:
            continue
        if name == 'proposal-finished':
            rows.append({'round': data['round'], 'candidates': data['candidate_ids']})
        elif name == 'execution-receipt':
            receipt = data['receipt']
            if allowed is None or receipt['run_id'] in allowed:
                rows.append({'run_id': receipt['run_id'], 'harness_id': receipt['harness_id'],
                    'evidence': [{'path': resource['path'], 'artifact_id': resource['artifact_id']}
                                 for resource in receipt['artifacts']]})
        elif name == 'execution-saved' and (allowed is None or data.get('run_id') in allowed):
            rows.append({'run_id': data['run_id'], 'reference': data['evidence']})
        elif name in {'completed-assessment', 'selection-decision'}:
            if allowed is None or data.get('run_id') in allowed:
                rows.append({'kind': name, 'reference': data['evidence']})
    return {'job_id': services.plan.job_id, 'conditions_id': services.plan.conditions_id,
            'links': rows, 'meaning': 'Navigation only. Candidate explanations remain hypotheses.'}


class RoundIndex:
    def __init__(self, context):
        self.context = context

    def before_proposal(self, event):
        payload = json.loads(getattr(event, 'snapshot_json', '{}'))
        value = round_navigation(self.context.services, payload.get('run_ids'))
        reference = self.context.artifacts.put(canonical_json(value).encode())
        self.context.services.record('evidence-round-index', reference=reference, round=event.round_index)
        return ContextContribution((Resource('rounds.json', reference, 'application/json', 'input'),))

    def install(self):
        self.context.services.hooks.register('before_proposal', self.before_proposal,
            active=True, identity='evidence-round-index')
