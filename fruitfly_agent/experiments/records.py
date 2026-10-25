"""Small run indexes and scoped stop requests; task evidence keeps its original owner."""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import threading
from uuid import uuid4

from fruitfly_agent.run.configuration.persistence import write_bytes


def timestamp():
    return datetime.now(timezone.utc).isoformat()


class RunRecords:
    def __init__(self, workspace):
        self.workspace = Path(workspace).resolve()
        self.root = self.workspace / '.fruitfly/experiments/runs'

    def directory(self, run_id):
        if not isinstance(run_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', run_id):
            raise ValueError('invalid experiment run ID')
        path = self.root / run_id
        if any(p.is_symlink() for p in (path, *path.parents)) or not path.resolve().is_relative_to(self.workspace):
            raise ValueError('experiment records must remain inside their workspace')
        return path

    def create(self, operation, configuration):
        run_id = operation + '-' + uuid4().hex
        directory = self.directory(run_id)
        directory.mkdir(parents=True, exist_ok=False)
        record = {'schema_version': 1, 'id': run_id, 'operation': operation, 'status': 'created',
            'started_at': timestamp(), 'configuration': configuration, 'links': {}}
        self.save(record)
        return record

    def save(self, record):
        path = self.directory(record['id']) / 'record.json'
        if path.is_symlink():
            raise ValueError('record must not be a symlink')
        write_bytes(path, (json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode())

    def read(self, run_id):
        path = self.directory(run_id) / 'record.json'
        if path.is_symlink():
            raise ValueError('record must not be a symlink')
        value = json.loads(path.read_text(encoding='utf-8'))
        if value.get('id') != run_id or value.get('schema_version') != 1:
            raise ValueError('experiment record identity/schema mismatch')
        if value.get('status') == 'running':
            owner = path.parent / 'owner.lock'
            if owner.is_symlink():
                raise ValueError('owner lock must not be a symlink')
            if not owner.exists():
                value['status'] = 'interrupted'
            else:
                with owner.open('r') as stream:
                    try:
                        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        pass
                    else:
                        value['status'] = 'interrupted'
        return value

    def list(self, operation=None):
        if not self.root.exists():
            return ()
        rows = []
        for path in sorted(self.root.iterdir()):
            if path.is_dir() and not path.name.startswith('.'):
                value = self.read(path.name)
                if operation is None or value['operation'] == operation:
                    rows.append(value)
        return tuple(sorted(rows, key=lambda r: r['started_at'], reverse=True))

    def stop(self, run_id):
        record = self.read(run_id)
        directory = self.directory(run_id)
        if any((directory / name).is_symlink() for name in ('owner.lock', 'stop.request')):
            raise ValueError('experiment control files must not be symlinks')
        # The owner holds this lock. Do not signal PIDs or touch other jobs.
        with (directory / 'owner.lock').open('a') as stream:
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                (directory / 'stop.request').touch(exist_ok=True)
                return {'id': run_id, 'state': 'stop_requested'}
            if record['status'] in {'created', 'running'}:
                return {'id': run_id, 'state': 'interrupted'}
            return {'id': run_id, 'state': record['status']}

    @contextmanager
    def owner(self, record):
        directory = self.directory(record['id'])
        if any((directory / name).is_symlink() for name in ('owner.lock', 'stop.request')):
            raise ValueError('experiment control files must not be symlinks')
        with (directory / 'owner.lock').open('a') as stream:
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ValueError('another process owns this experiment') from exc
            request = directory / 'stop.request'
            request.unlink(missing_ok=True)
            finished = threading.Event()
            def monitor():
                while not finished.wait(0.2):
                    if request.exists():
                        os.kill(os.getpid(), signal.SIGINT)
                        return
            watcher = threading.Thread(target=monitor, daemon=True)
            def interrupt(signum, frame):
                raise KeyboardInterrupt('experiment interrupted')
            previous = signal.signal(signal.SIGTERM, interrupt)
            record.update(status='running')
            self.save(record)
            watcher.start()
            try:
                yield record
            except BaseException as exc:
                record.update(status='cancelled' if isinstance(exc, (KeyboardInterrupt, SystemExit)) or type(exc).__name__ == 'CancelledError' else 'failed',
                    error=str(exc), finished_at=timestamp())
                self.save(record)
                raise
            else:
                record.setdefault('finished_at', timestamp())
                if record['status'] == 'running':
                    record['status'] = 'completed'
                self.save(record)
            finally:
                finished.set()
                watcher.join(timeout=1)
                signal.signal(signal.SIGTERM, previous)
