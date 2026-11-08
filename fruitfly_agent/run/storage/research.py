"""Single-owner durable research journals under the existing Improvement jobs root."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import fcntl
from fruitfly_agent.improvement.contracts.validation import identifier
from fruitfly_agent.improvement.contracts.versions import canonical_json, content_hash
from fruitfly_agent.improvement.stages.recovery import reconstruct


class ResearchStore:
    def __init__(self, workspace, research_id, *, directory=None):
        identifier(research_id)
        self.workspace = Path(workspace).resolve()
        self.directory = Path(directory).resolve() if directory is not None else self.workspace / '.fruitfly/improvement/jobs' / research_id
        self.allowed_root = self.directory if directory is not None else self.workspace
        self._cache = None
        self._previous = ''
        self._owned = False
        self._safe()

    def _safe(self):
        if not self.directory.resolve().is_relative_to(self.allowed_root):
            raise ValueError('research directory escapes workspace')
        for path in (self.directory, *self.directory.parents):
            if path.is_relative_to(self.allowed_root) and path.is_symlink():
                raise ValueError('research directory must not traverse symlinks')
        for name in ('research-events.jsonl', '.research-owner'):
            if (self.directory / name).is_symlink():
                raise ValueError('research files must not be symlinks')

    @contextmanager
    def owner(self):
        self._safe()
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / '.research-owner'
        with path.open('a+') as stream:
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ValueError('another process owns this research') from exc
            stream.seek(0); stream.truncate()
            stream.write(canonical_json({'pid': os.getpid()})); stream.flush()
            try:
                self._cache = None
                self.events()
                self._owned = True
                yield self
            finally:
                self._owned = False
                self._cache = None
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def events(self):
        self._safe()
        if self._owned and self._cache is not None:
            return tuple(self._cache)
        path = self.directory / 'research-events.jsonl'
        if not path.exists():
            self._cache, self._previous = [], ''
            return ()
        rows = []
        prior = ''
        for index, line in enumerate(path.read_text().splitlines(), 1):
            value = json.loads(line)
            if set(value) != {'sequence', 'previous', 'event', 'identity'}:
                raise ValueError('invalid research journal envelope')
            expected = content_hash(canonical_json({k: value[k] for k in ('sequence', 'previous', 'event')}))
            if value['sequence'] != index or value['previous'] != prior or value['identity'] != expected:
                raise ValueError('research journal integrity failure')
            rows.append(value['event'])
            prior = value['identity']
        reconstruct(rows)
        self._cache, self._previous = rows, prior
        return tuple(rows)

    def append(self, event):
        if not self._owned:
            raise ValueError('research mutation requires an owned journal')
        rows = self._cache if self._cache is not None else list(self.events())
        if event.get('type') == 'role-event':
            from fruitfly_agent.improvement.contracts.versions import require_hash
            require_hash(event['data']['artifact_id'])
        else:
            reconstruct((*rows, event))
        path = self.directory / 'research-events.jsonl'
        previous = self._previous
        value = {'sequence': len(rows) + 1, 'previous': previous, 'event': event}
        value['identity'] = content_hash(canonical_json(value))
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            data = (canonical_json(value) + '\n').encode()
            with os.fdopen(fd, 'ab', closefd=False) as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        finally:
            os.close(fd)
        rows.append(json.loads(canonical_json(event)))
        self._cache = rows
        self._previous = value['identity']

    def fork(self, research_id):
        target = ResearchStore(self.workspace, research_id, directory=self.directory.parent / research_id) if self.allowed_root != self.workspace else ResearchStore(self.workspace, research_id)
        if (target.directory / 'research-events.jsonl').exists():
            raise ValueError('research fork already exists')
        with target.owner():
            for event in self.events():
                target.append(event)
        return target
