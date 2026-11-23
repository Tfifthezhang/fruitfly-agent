"""Locked atomic retained-state checkpoints; content lives in ArtifactStore."""
from contextlib import contextmanager
from copy import deepcopy
import fcntl
import hashlib
import json
import os
import re
from pathlib import Path
import tempfile
from uuid import uuid4

from fruitfly_agent.improvement.contracts.versions import StateSnapshot, SnapshotFile, canonical_json, content_hash


class RetainedStateStore:
    def __init__(self, root: Path, artifacts, *, snapshot_directory: str | None = None):
        self.root = Path(root)
        self.artifacts = artifacts
        self.snapshot_directory = snapshot_directory

    def store_for(self, key):
        return self

    def _safe(self):
        if any(p.is_symlink() for p in (self.root, *self.root.parents)):
            raise ValueError('retained state cannot use symlinks')

    @contextmanager
    def _lock(self):
        self._safe()
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / 'state.lock'
        if path.is_symlink():
            raise ValueError('retained state lock cannot be a symlink')
        with path.open('a') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)

    @contextmanager
    def maintenance_lease(self):
        """Reserve one worker without holding the checkpoint write lock."""
        self._safe()
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / 'maintenance.lock'
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'r+') as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                yield False
                return
            yield True

    def read(self):
        self._safe()
        path = self.root / 'state.json'
        if not path.exists() and not path.is_symlink():
            return {'schema_version': 1, 'libraries': {}, 'evidence': [], 'processed': 0,
                'consolidated_turns': 0, 'pending': {}, 'operations': {}}
        if path.is_symlink() or path.stat().st_size > 8_000_000:
            raise ValueError('invalid retained state file')
        value = json.loads(path.read_text())
        if (not isinstance(value, dict) or set(value) != {'schema_version', 'libraries', 'evidence', 'processed',
                'consolidated_turns', 'pending', 'operations'} or value['schema_version'] != 1
                or not isinstance(value['libraries'], dict) or not isinstance(value['evidence'], list)
                or type(value['processed']) is not int or not 0 <= value['processed'] <= len(value['evidence'])
                or type(value['consolidated_turns']) is not int or value['consolidated_turns'] < 0
                or not isinstance(value['pending'], dict) or not isinstance(value['operations'], dict)):
            raise ValueError('invalid retained state record')
        self._validate(value)
        return value

    def _validate(self, value):
        def nonempty(text):
            return isinstance(text, str) and bool(text)
        def artifact(reference):
            if not isinstance(reference, str) or not re.fullmatch(r'sha256:[a-f0-9]{64}', reference):
                raise ValueError('invalid retained artifact identity')
            return self.artifacts.read_text(reference)
        if (type(value['processed']) is not int or not 0 <= value['processed'] <= len(value['evidence'])
                or type(value['consolidated_turns']) is not int or value['consolidated_turns'] < 0):
            raise ValueError('invalid retained progress')
        for key, reference in value['libraries'].items():
            if not nonempty(key):
                raise ValueError('invalid retained library identity')
            artifact(reference)
        identities = set()
        for row in value['evidence']:
            if (not isinstance(row, dict) or set(row) != {'identity', 'session_id', 'message_id', 'artifact', 'chars', 'completed'}
                    or any(not nonempty(row[k]) for k in ('identity', 'session_id', 'message_id'))
                    or row['identity'] != row['session_id'] + ':' + row['message_id']
                    or row['identity'] in identities or type(row['chars']) is not int or row['chars'] < 0
                    or type(row['completed']) is not bool):
                raise ValueError('invalid retained source evidence')
            identities.add(row['identity'])
            if len(artifact(row['artifact'])) != row['chars']:
                raise ValueError('retained source character count changed')
        if value['consolidated_turns'] > sum(row['completed'] for row in value['evidence']):
            raise ValueError('retained consolidation progress exceeds completed turns')
        for identity, row in value['operations'].items():
            if (not nonempty(identity) or not isinstance(row, dict)
                    or set(row) not in ({'operation', 'request_id', 'status'}, {'operation', 'request_id', 'status', 'journal'},
                        {'operation', 'request_id', 'status', 'end_reason'}, {'operation', 'request_id', 'status', 'journal', 'end_reason'})
                    or any(not nonempty(row[k]) for k in row)
                    or row['operation'] not in {'extract', 'consolidate', 'import'}
                    or row['status'] not in {'running', 'unknown', 'completed', 'failed', 'cancelled', 'retry-authorized', 'retry-generation', 'discarded'}):
                raise ValueError('invalid retained maintenance operation')
            if 'journal' in row:
                self.read_journal(row)
        for identity, row in value['pending'].items():
            if (identity not in value['operations'] or not isinstance(row, dict)
                    or set(row) != {'status', 'key', 'artifact', 'parent', 'basis', 'operation'}
                    or row['status'] not in ('pending', 'committed', 'rejected') or not nonempty(row['key'])
                    or row['basis'] != 'human-review'
                    or row['operation'] != value['operations'][identity]['operation']
                    or value['operations'][identity]['status'] != 'completed'):
                raise ValueError('invalid retained pending update')
            artifact(row['artifact'])
            if row['parent'] is not None:
                artifact(row['parent'])
        if sum(row['status'] == 'pending' for row in value['pending'].values()) > 1:
            raise ValueError('conflicting retained pending updates')

    def _write(self, value):
        self._validate(value)
        text = canonical_json(value)
        if len(text.encode()) > 8_000_000:
            raise ValueError('retained checkpoint exceeds byte budget')
        fd, name = tempfile.mkstemp(prefix='.state-', dir=self.root)
        try:
            with os.fdopen(fd, 'w') as stream:
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.root / 'state.json')
            directory = os.open(self.root, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            Path(name).unlink(missing_ok=True)

    def mutate(self, change):
        with self._lock():
            value = self.read()
            result = change(value)
            self._write(value)
            return result

    def observe(self, evidence):
        def change(value):
            known = {e['identity']: e for e in value['evidence']}
            for entry in evidence:
                old = known.get(entry['identity'])
                if old is not None:
                    if any(old[k] != entry[k] for k in old if k != 'completed'):
                        raise ValueError('retained evidence identity changed')
                    old['completed'] = old['completed'] or entry['completed']
                    continue
                if len(value['evidence']) >= 100000:
                    raise ValueError('retained evidence count limit reached')
                row = deepcopy(entry)
                value['evidence'].append(row)
                known[row['identity']] = row
        self.mutate(change)

    def library(self, key):
        reference = self.read()['libraries'].get(key)
        return self.artifacts.read_text(reference) if reference else None

    def begin(self, operation, request_id, *, request=None, checkpoint=None, conditions_id=''):
        journal = None
        if request is not None:
            from datetime import datetime, timezone
            journal = self.artifacts.put_text(canonical_json({'request': request,
                'checkpoint': checkpoint, 'calls': [], 'conditions_id': conditions_id,
                'observed_at': datetime.now(timezone.utc).isoformat()})).artifact_id
        def change(value):
            if any(row['status'] in {'running', 'unknown'} for row in value['operations'].values()):
                raise ValueError('maintenance request has an unknown outcome; explicit retry required')
            identity = uuid4().hex
            value['operations'][identity] = {'operation': operation, 'request_id': request_id, 'status': 'running'}
            if journal is not None:
                value['operations'][identity]['journal'] = journal
            return identity
        return self.mutate(change)

    def read_journal(self, operation):
        value = json.loads(self.artifacts.read_text(operation['journal']))
        if (not isinstance(value, dict) or set(value) != {'request', 'checkpoint', 'calls', 'observed_at', 'conditions_id'}
                or not isinstance(value['request'], dict) or not isinstance(value['checkpoint'], dict)
                or not isinstance(value['calls'], list) or not isinstance(value['observed_at'], str)
                or not isinstance(value['conditions_id'], str)):
            raise ValueError('invalid maintenance journal')
        for call in value['calls']:
            if (not isinstance(call, dict) or set(call) not in ({'input', 'started'}, {'input', 'started', 'response'})
                    or type(call.get('started')) is not bool
                    or not re.fullmatch(r'sha256:[a-f0-9]{64}', call.get('input', ''))):
                raise ValueError('invalid maintenance call')
            if 'response' in call:
                self.artifacts.read_text(call['response'])
        checkpoint = value['checkpoint']
        if (set(checkpoint) != {'schema_version', 'libraries', 'evidence', 'processed', 'consolidated_turns', 'pending', 'operations'}
                or checkpoint['schema_version'] != 1
                or any('journal' in row for row in checkpoint['operations'].values())):
            raise ValueError('invalid captured maintenance checkpoint')
        self._validate(checkpoint)
        return value

    def record_journal(self, identity, journal):
        reference = self.artifacts.put_text(canonical_json(journal)).artifact_id
        def change(value):
            row = value['operations'][identity]
            if row['status'] != 'running':
                raise ValueError('maintenance operation is not running')
            row['journal'] = reference
        self.mutate(change)

    def resume(self, identity):
        def change(value):
            row = value['operations'][identity]
            journal = self.read_journal(row)
            unfinished = bool(journal['calls'] and 'response' not in journal['calls'][-1])
            uncertain = unfinished and journal['calls'][-1]['started']
            if row['status'] not in {'retry-authorized', 'retry-generation'} and (row['status'] not in {'running', 'cancelled'} or uncertain):
                raise ValueError('maintenance outcome requires explicit retry')
            if unfinished or row['status'] == 'retry-generation' and journal['calls']:
                journal['calls'].pop()
            row['status'] = 'running'
            row['journal'] = self.artifacts.put_text(canonical_json(journal)).artifact_id
            return journal
        return self.mutate(change)

    def discard(self, identity):
        """Release a known failed batch while retaining its responses and evidence."""
        def change(value):
            row = value['operations'].get(identity)
            if row is None or row['status'] not in {'running', 'failed', 'cancelled', 'retry-authorized', 'retry-generation'} or 'journal' not in row:
                raise ValueError('only an inactive known batch can be discarded')
            journal = self.read_journal(row)
            if row['status'] != 'retry-authorized' and any(call['started'] and 'response' not in call for call in journal['calls']):
                raise ValueError('unknown calls require explicit retry')
            row['status'] = 'discarded'
            return 'discarded'
        with self.maintenance_lease() as acquired:
            if not acquired:
                raise ValueError('maintenance is still running')
            return self.mutate(change)

    def end_legacy_operation(self, identity):
        """Close a previously authorized operation whose journal is absent."""
        def change(value):
            row = value['operations'].get(identity)
            if row is None or 'journal' in row or row['status'] not in {'unknown', 'retry-authorized'}:
                raise ValueError('only an authorized legacy operation without a journal can be ended')
            row['status'] = 'discarded'
            row['end_reason'] = 'legacy-no-journal'
            return 'ended'
        with self.maintenance_lease() as acquired:
            if not acquired:
                raise ValueError('maintenance is busy in another process')
            return self.mutate(change)

    def allow_retry(self, identity):
        """Authorize replay after an unknown outcome; repeated authorization is safe."""
        def change(value):
            row = value['operations'].get(identity)
            if row is None:
                raise ValueError('maintenance operation is unavailable')
            if row['status'] in {'retry-authorized', 'retry-generation'}:
                return row['status']
            if (row['status'] not in {'running', 'unknown'}
                    and not (row['status'] == 'failed' and 'journal' in row)):
                raise ValueError('maintenance operation has no unknown outcome')
            row['status'] = 'retry-generation' if row['status'] == 'failed' and 'journal' in row else 'retry-authorized'
            return row['status']
        with self.maintenance_lease() as acquired:
            if not acquired:
                raise ValueError('maintenance is still running')
            return self.mutate(change)


    def finish(self, identity, *, status, key=None, text=None, parent=None, processed=None, turns=None, publish=False):
        if status not in {'completed', 'failed', 'cancelled', 'unknown'}:
            raise ValueError('invalid maintenance terminal status')
        reference = self.artifacts.put_text(text).artifact_id if text is not None else None
        def change(value):
            record = value['operations'][identity]
            if record['status'] != 'running':
                raise ValueError('maintenance operation already finished')
            if status == 'completed':
                if any(v['status'] == 'pending' for v in value['pending'].values()):
                    raise ValueError('review pending state before preparing another update')
                if key and value['libraries'].get(key) != parent:
                    raise ValueError('retained parent changed during maintenance')
                if reference:
                    if publish:
                        value['libraries'][key] = reference
                    else:
                        value['pending'][identity] = {'status': 'pending', 'key': key, 'artifact': reference,
                            'parent': parent, 'basis': 'human-review', 'operation': record['operation']}
                if processed is not None:
                    value['processed'] = processed
                if turns is not None:
                    value['consolidated_turns'] = turns
            record['status'] = status
        self.mutate(change)

    def publish(self, identity):
        """Adopt a validated batch atomically without changing a live runtime."""
        return self.review(identity, 'commit')

    def review(self, identity, action):
        return self.review_with_activation(identity, action, lambda: None)

    def adopt_with_activation(self, documents, expected, activate):
        """Publish checked configuration-owned S while preserving control state."""
        references = {key: self.artifacts.put_text(text).artifact_id for key, text in documents.items()}
        with self._lock():
            previous = self.read()
            if previous['libraries'] != expected:
                raise ValueError('retained state changed before activation')
            value = deepcopy(previous)
            value['libraries'].update(references)
            self._write(value)
            try:
                activate()
            except BaseException:
                self._write(previous)
                raise

    def review_with_activation(self, identity, action, activate):
        if action not in {'commit', 'reject'}:
            raise ValueError('state action must be commit or reject')
        def change(value):
            row = value['pending'].get(identity)
            if row is None or row['status'] != 'pending':
                raise ValueError('retained update is not pending')
            if action == 'commit':
                if value['libraries'].get(row['key']) != row['parent']:
                    raise ValueError('retained update parent changed')
                self.artifacts.read_text(row['artifact'])
                value['libraries'][row['key']] = row['artifact']
            row['status'] = 'committed' if action == 'commit' else 'rejected'
            return row['status']
        with self._lock():
            previous = self.read()
            value = deepcopy(previous)
            result = change(value)
            self._write(value)
            try:
                activate()
            except BaseException:
                self._write(previous)
                raise
            return result

    def freeze(self):
        value = self.read()
        # Executable documents are captured by their owner targets. Keep control
        # state stable across a checked document activation, and freeze every
        # evidence or pending artifact required to resume maintenance separately.
        value['libraries'] = {}
        references = {row['artifact'] for row in value['evidence']}
        references.update(row['artifact'] for row in value['pending'].values())
        for row in value['operations'].values():
            if 'journal' in row:
                references.add(row['journal'])
                journal = self.read_journal(row)
                references.update(call['response'] for call in journal['calls'] if 'response' in call)
                checkpoint = journal['checkpoint']
                references.update(checkpoint['libraries'].values())
                references.update(e['artifact'] for e in checkpoint['evidence'])
        files = [SnapshotFile('.fruitfly/artifacts/' + ref[7:], self.artifacts.read_text(ref))
                 for ref in sorted(references)]
        directory = self.snapshot_directory
        if directory is None:
            directory = self.root.relative_to(self.root.parents[2]).as_posix()
        checkpoint = directory + '/state.json'
        return StateSnapshot((SnapshotFile(checkpoint, canonical_json(value)), *files),
            roots=(str(Path(checkpoint).parent),))
