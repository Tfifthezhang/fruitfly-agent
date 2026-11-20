"""Lab-owned evidence supply receipts; availability is not semantic correctness."""
from dataclasses import dataclass, asdict
from collections import deque
import hashlib


class EvidenceUnavailable(ValueError):
    pass


@dataclass(frozen=True)
class AccessReceipt:
    path: str
    status: str
    content_id: str = ''
    offset: int = 0
    length: int = 0


class EvidenceAccess:
    def __init__(self, run_ids=(), *, record=None, budget=None, limits=None):
        self.run_ids = frozenset(run_ids)
        self.supplied = set()
        self.budget = budget if budget is not None else {'characters': 0, 'responses': 0, 'model_requests': 0, 'tool_calls': 0}
        self.delegated_supplied = set()
        self.limits = dict(limits or {})
        self.local_characters = 0
        self.local_responses = 0
        self.paths: dict[str, str] = {}
        self.reading = {}
        self.receipts: deque[AccessReceipt] = deque(maxlen=256)
        self.record = record or (lambda *args, **kwargs: None)

    @property
    def supply_characters(self):
        return self.budget['characters']

    @supply_characters.setter
    def supply_characters(self, value):
        self.local_characters += max(0, value - self.budget['characters'])
        self.budget['characters'] = value

    @property
    def supply_responses(self):
        return self.budget['responses']

    @supply_responses.setter
    def supply_responses(self, value):
        self.local_responses += max(0, value - self.budget['responses'])
        self.budget['responses'] = value

    def remaining_characters(self, maximum):
        return min(maximum - self.supply_characters,
            self.limits.get('characters', maximum) - self.local_characters)

    def remaining_responses(self, maximum):
        return min(maximum - self.supply_responses,
            self.limits.get('responses', maximum) - self.local_responses)

    def denied(self, path):
        self._record(AccessReceipt(path, 'not_granted'))

    def failed(self, path):
        self.paths[path] = 'unavailable'
        self._record(AccessReceipt(path, 'unavailable'))

    def grant(self, paths):
        for path in paths:
            self.paths.setdefault(path, 'unaccessed')

    def available(self, path):
        self.paths[path] = 'available'

    def provided(self, path, content, *, offset=0, reading_kind="read"):
        ranges = self.reading.setdefault(path, {"read": [], "search": []})[reading_kind]
        if isinstance(content, str):
            ranges.append((offset, offset + len(content)))
            merged: list[tuple[int, int]] = []
            for start, end in sorted(ranges):
                if merged and start <= merged[-1][1]:
                    merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
                else:
                    merged.append((start, end))
            ranges[:] = merged
        self.paths[path] = 'provided'
        data = content if isinstance(content, bytes) else content.encode('utf-8')
        self._record(AccessReceipt(path, 'provided', 'sha256:' + hashlib.sha256(data).hexdigest(), offset, len(data)))
        text = content if isinstance(content, str) else ''
        for run in self.run_ids:
            if (path.startswith('context/executions/' + run + '/')
                    or path == 'context/summaries/' + run + '.json'
                    or path.startswith('context/tasks/') and '/executions/' + run + '/' in path
                    or path in {'context/executions.json', 'context/evaluations.json'} and ('"run_id":"' + run + '"') in text):
                self.supplied.add(run)

    def _record(self, receipt):
        self.receipts.append(receipt)
        self.record('evidence-access', **asdict(receipt))

    def validate_citations(self, reasons):
        cited = {name for reason in reasons for name in reason.evidence_ids}
        if cited - (self.supplied | self.delegated_supplied):
            raise EvidenceUnavailable('candidate cites executions not successfully supplied to this editing stage')

    def inspection(self):
        return {'paths': {path: {kind: list(spans) for kind, spans in kinds.items()}
                for path, kinds in sorted(self.reading.items())},
            'execution_ids_supplied': sorted(self.supplied),
            'execution_ids_delegated': sorted(self.delegated_supplied),
            'scope': 'Returned text ranges; neither complete reading nor understanding is inferred.'}
