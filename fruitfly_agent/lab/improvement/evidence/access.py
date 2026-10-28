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
    def __init__(self, run_ids=(), *, record=None):
        self.run_ids = frozenset(run_ids)
        self.supplied = set()
        self.paths: dict[str, str] = {}
        self.receipts: deque[AccessReceipt] = deque(maxlen=256)
        self.record = record or (lambda *args, **kwargs: None)

    def failed(self, path):
        self.paths[path] = 'unavailable'
        self._record(AccessReceipt(path, 'unavailable'))

    def grant(self, paths):
        for path in paths:
            self.paths.setdefault(path, 'unaccessed')

    def available(self, path):
        self.paths[path] = 'available'

    def provided(self, path, content, *, offset=0):
        self.paths[path] = 'provided'
        data = content if isinstance(content, bytes) else content.encode('utf-8')
        self._record(AccessReceipt(path, 'provided', 'sha256:' + hashlib.sha256(data).hexdigest(), offset, len(data)))
        text = content if isinstance(content, str) else ''
        for run in self.run_ids:
            if (path.startswith('context/executions/' + run + '/')
                    or path.startswith('context/tasks/') and '/executions/' + run + '/' in path
                    or path in {'context/executions.json', 'context/evaluations.json'} and ('"run_id":"' + run + '"') in text):
                self.supplied.add(run)

    def _record(self, receipt):
        self.receipts.append(receipt)
        self.record('evidence-access', **asdict(receipt))

    def validate_citations(self, reasons):
        cited = {name for reason in reasons for name in reason.evidence_ids}
        if cited - self.supplied:
            raise EvidenceUnavailable('candidate cites executions not successfully supplied to this editing stage')
