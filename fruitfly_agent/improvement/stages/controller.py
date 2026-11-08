"""Execute independently reusable research activities through injected capabilities."""
import asyncio
from dataclasses import asdict
from uuid import uuid4
from ..contracts.activities import ActivitySpec, ActivityResult, UnresolvedActivity
from .recovery import reconstruct


class ResearchController:
    def __init__(self, journal, artifacts, implementations):
        self.journal, self.artifacts = journal, artifacts
        self.implementations = dict(implementations)

    def state(self):
        return reconstruct(self.journal.events())

    def revise(self, revision):
        state = self.state()
        if any(row['identity'] == revision.identity for row in state.revisions):
            return revision.identity
        event = {'type': 'revision', 'data': {'identity': revision.identity, 'revision': asdict(revision)}}
        reconstruct((*self.journal.events(), event))
        self.journal.append(event)
        return revision.identity

    def note(self, key, text):
        if not isinstance(key, str) or not key or not isinstance(text, str):
            raise ValueError('research notes require a key and text')
        self.journal.append({'type': 'note', 'data': {'key': key, 'text': text}})

    async def perform(self, spec, *, fresh=False, retry_unresolved=False):
        if not isinstance(spec, ActivitySpec):
            raise TypeError('research activities require ActivitySpec')
        state = self.state()
        if not state.revisions:
            raise ValueError('create a research revision before activity execution')
        for dependency in spec.dependencies:
            row = state.attempts.get(dependency)
            if row is None or row['status'] == 'running':
                raise ValueError('research dependency is unavailable or unresolved')
        uncertain = [r for r in state.attempts.values()
            if r['spec_identity'] == spec.identity and r['status'] == 'running']
        if uncertain and not retry_unresolved:
            raise ValueError('activity outcome is unresolved; reconcile or explicitly authorize a new attempt')
        if not fresh:
            previous = state.reusable(spec)
            if previous:
                result = ActivityResult.from_dict(previous['result'])
                for resource in result.outputs:
                    self.artifacts.read(resource.artifact_id)
                self.journal.append({'type': 'activity-reused', 'data': {'attempt_id': previous['attempt_id']}})
                return result
        implementation = self.implementations.get((spec.kind, spec.implementation_id))
        if implementation is None:
            raise ValueError('research activity implementation is not registered')
        for resource in spec.inputs:
            self.artifacts.read(resource.artifact_id)
        attempt = uuid4().hex
        self.journal.append({'type': 'activity-started', 'data': {'attempt_id': attempt,
            'revision_id': state.revisions[-1]['identity'], 'spec_identity': spec.identity, 'spec': spec.to_dict()}})
        try:
            result = await implementation(spec)
            if not isinstance(result, ActivityResult):
                raise TypeError('research activity did not return ActivityResult')
            for resource in result.outputs:
                self.artifacts.read(resource.artifact_id)
            self.journal.append({'type': 'activity-finished', 'data': {'attempt_id': attempt,
                'status': 'completed', 'result': asdict(result)}})
            return result
        except BaseException as exc:
            from ..contracts.failures import CleanupError
            if isinstance(exc, (UnresolvedActivity, CleanupError)):
                self.note('unresolved-' + attempt, str(exc))
                raise
            # Persist known interruption. A lost process leaves its intent running;
            # recovery refuses automatic replay of that uncertain external work.
            self.journal.append({'type': 'activity-finished', 'data': {'attempt_id': attempt,
                'status': 'interrupted' if isinstance(exc, asyncio.CancelledError) else 'failed',
                'error_type': type(exc).__name__, 'detail': str(exc)}})
            raise
