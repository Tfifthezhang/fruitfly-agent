"""Rebuild research state from a validated journal, without restoring live objects."""
from dataclasses import dataclass, field
from ..contracts.activities import ActivityResult, ActivitySpec
from ..contracts.versions import canonical_json, content_hash


@dataclass
class ResearchState:
    revisions: list[dict] = field(default_factory=list)
    attempts: dict[str, dict] = field(default_factory=dict)
    notes: dict[str, str] = field(default_factory=dict)

    @property
    def unresolved(self):
        return tuple(key for key, value in self.attempts.items() if value['status'] == 'running')

    def reusable(self, spec):
        return next((row for row in reversed(tuple(self.attempts.values()))
            if row['spec_identity'] == spec.identity and row['status'] == 'completed'), None)


def reconstruct(events):
    state = ResearchState()
    for event in events:
        kind, data = event['type'], event['data']
        if kind == 'revision':
            from ..contracts.research import ResearchRevision
            revision = ResearchRevision(**data['revision'])
            if revision.identity != data['identity']:
                raise ValueError('research revision identity mismatch')
            if revision.parent and revision.parent not in {r['identity'] for r in state.revisions}:
                raise ValueError('research revision parent unavailable')
            state.revisions.append(data)
        elif kind == 'activity-started':
            spec = ActivitySpec.from_dict(data['spec'])
            if spec.identity != data['spec_identity'] or data['attempt_id'] in state.attempts:
                raise ValueError('invalid research activity identity')
            state.attempts[data['attempt_id']] = {**data, 'status': 'running'}
        elif kind == 'activity-finished':
            row = state.attempts[data['attempt_id']]
            if row['status'] != 'running' or data['status'] not in {'completed', 'failed', 'interrupted'}:
                raise ValueError('invalid research activity transition')
            if data['status'] == 'completed':
                ActivityResult.from_dict(data['result'])
            row.update(data)
        elif kind == 'role-event':
            from ..contracts.versions import require_hash
            require_hash(data['artifact_id'])
        elif kind == 'note':
            state.notes[data['key']] = data['text']
        elif kind == 'activity-reused':
            if data['attempt_id'] not in state.attempts:
                raise ValueError('unknown reused research attempt')
        else:
            raise ValueError('unknown research event: ' + kind)
    return state
