"""Bounded attributed observations; model explanations remain hypotheses."""
from collections import deque
from dataclasses import dataclass, asdict
import json

from fruitfly_agent.improvement.contracts.lifecycle import ContextContribution
from fruitfly_agent.improvement.contracts.tasks import Resource
from fruitfly_agent.improvement.contracts.versions import canonical_json, content_hash


@dataclass(frozen=True)
class ResearchEntry:
    kind: str
    evidence_id: str
    conditions_id: str
    payload_json: str


class ResearchLedger:
    def __init__(self, context, *, max_entries=128, retrieve_entries=8, guidance=''):
        self.context = context
        self.entries: deque[ResearchEntry] = deque(maxlen=max_entries)
        self.retrieve_entries, self.guidance = retrieve_entries, guidance
        self.sequence = 0
        self.best_run_id = None

    def append(self, kind, evidence, value):
        entry = ResearchEntry(kind, evidence, self.context.plan.conditions_id, canonical_json(value))
        self.entries.append(entry)
        self.sequence += 1
        reference = self.context.artifacts.put(canonical_json(asdict(entry)).encode())
        self.context.services.record('research-entry', sequence=self.sequence, artifact_id=reference, kind=kind)
        if self.context.save_record is not None:
            self.context.save_record('research/' + reference.removeprefix('sha256:') + '.json', asdict(entry))

    def after_trial(self, event):
        receipt = json.loads(event.snapshot_json)['receipt']
        self.append('observation', receipt['run_id'], receipt)

    def after_candidate(self, event):
        value = json.loads(event.snapshot_json)
        self.append('hypothesis', value['candidate_id'], value)

    def after_round(self, event):
        value = json.loads(event.snapshot_json)
        self.best_run_id = value.get('incumbent_run_id') or self.best_run_id
        self.append('experiment', self.best_run_id or '', value)

    def before_proposal(self, event):
        value = {'job_id': event.job_id, 'conditions_id': self.context.plan.conditions_id,
            'best_run_id': self.best_run_id, 'next_experiment_guidance': self.guidance,
            'entries': [asdict(e) for e in list(self.entries)[-self.retrieve_entries:]],
            'limits': 'Recorded observations and candidate hypotheses; no independent assurance or shared learning.'}
        data = canonical_json(value).encode()
        reference = self.context.artifacts.put(data)
        return ContextContribution((Resource('research.json', reference, 'application/json', 'input'),))

    def install(self):
        hooks = self.context.services.hooks
        hooks.register('after_trial', self.after_trial, identity='research-ledger')
        hooks.register('after_candidate_validated', self.after_candidate, identity='research-ledger')
        hooks.register('after_round', self.after_round, identity='research-ledger')
        hooks.register('before_proposal', self.before_proposal, active=True, identity='research-retrieval')
