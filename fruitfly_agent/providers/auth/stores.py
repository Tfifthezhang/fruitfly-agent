"""Explicit credential backends with atomic updates and interprocess locking."""
from __future__ import annotations
from contextlib import contextmanager
import json
import os
from pathlib import Path
import stat
import tempfile
import time
from typing import Any, Callable, Iterator
import hashlib

def read_private_json(path: Path) -> Any:
    """Read an owner-only regular file through a non-following descriptor."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd) as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('Credential file requires owner-only permissions')
        return json.load(source)


class FileCredentialStore:
    def __init__(self, directory: Path):
        self.directory = directory

    def _prepare(self) -> None:
        if self.directory.is_symlink():
            raise ValueError('Credential directory must not be a symlink')
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        info = self.directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('Credential directory requires owner-only permissions')

    def _path(self, account: str) -> Path:
        return self.directory / (hashlib.sha256(account.encode()).hexdigest() + '.json')

    @contextmanager
    def lock(self, account: str) -> Iterator[None]:
        import fcntl
        self._prepare()
        path = self._path(account).with_suffix('.lock')
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise ValueError('Credential lock requires owner-only permissions')
            until = time.monotonic() + 20
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= until:
                        raise ValueError('Credential store is busy; retry later') from None
                    time.sleep(.05)
            yield
        finally:
            os.close(fd)

    def read(self, account: str) -> dict[str, Any] | None:
        if self.directory.exists() or self.directory.is_symlink():
            self._prepare()
        path = self._path(account)
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            return None
        with os.fdopen(fd) as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise ValueError('Credential file requires owner-only permissions')
            value = json.load(source)
        if not isinstance(value, dict) or value.get('account') != account:
            raise ValueError('Invalid credential record')
        return value

    def _write(self, account: str, value: dict[str, Any]) -> None:
        data = json.dumps(value, allow_nan=False).encode()
        fd, name = tempfile.mkstemp(prefix='.auth-', dir=self.directory)
        try:
            with os.fdopen(fd, 'wb') as out:
                out.write(data)
                out.flush()
                os.fsync(out.fileno())
            os.replace(name, self._path(account))
        finally:
            Path(name).unlink(missing_ok=True)

    def modify(self, account: str, update: Callable[[dict[str, Any] | None], dict[str, Any]]) -> dict[str, Any]:
        with self.lock(account):
            result = update(self.read(account))
            if result.get('account') != account:
                raise ValueError('Credential account mismatch')
            self._write(account, result)
            return result

    def list(self) -> tuple[dict[str, str], ...]:
        result = []
        if self.directory.exists() or self.directory.is_symlink():
            self._prepare()
            for path in self.directory.glob('*.json'):
                try:
                    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                    with os.fdopen(fd) as source:
                        info = os.fstat(source.fileno())
                        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                                or info.st_mode & 0o077):
                            continue
                        value = json.load(source)
                    if not isinstance(value, dict) or not isinstance(value.get('account'), str):
                        continue
                    if self._path(value['account']) != path:
                        continue
                    result.append({k: str(value.get(k, '')) for k in ('account', 'integration', 'label', 'status')})
                except (OSError, ValueError, TypeError):
                    continue
        return tuple(result)

class KeyringCredentialStore(FileCredentialStore):
    """Keep account metadata locally and tokens in the selected OS keyring."""
    def __init__(self, directory: Path):
        super().__init__(directory)
        try:
            import keyring
        except ImportError:
            raise ValueError('Install keyring or explicitly select protected-file storage') from None
        if keyring.get_keyring().priority <= 0:
            raise ValueError('System credential storage is unavailable; select protected-file storage explicitly')
        self.backend = keyring

    def read(self, account: str) -> dict[str, Any] | None:
        metadata = super().read(account)
        if metadata is None:
            return None
        try:
            secret = self.backend.get_password('fruitfly-agent', account)
        except Exception:
            raise ValueError('System credential storage could not be read') from None
        value = json.loads(secret) if secret else {**metadata, 'status': 'signed_out'}
        if not isinstance(value, dict) or value.get('account') != account:
            raise ValueError('System credential account mismatch')
        return value

    def _write(self, account: str, value: dict[str, Any]) -> None:
        try:
            self.backend.set_password('fruitfly-agent', account, json.dumps(value, allow_nan=False))
        except Exception:
            raise ValueError('System credential storage could not be updated') from None
        super()._write(account, {k: value.get(k, '') for k in ('account', 'integration', 'label', 'status')})

def auth_directory() -> Path:
    return Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'fruitfly-agent'

def configured_store(directory: Path | None = None) -> FileCredentialStore:
    directory = directory or auth_directory()
    if directory.exists() or directory.is_symlink():
        FileCredentialStore(directory)._prepare()
    choice = directory / 'storage.json'
    try:
        value = read_private_json(choice)
    except FileNotFoundError:
        return KeyringCredentialStore(directory / 'accounts')
    if value == {'backend': 'file'}:
        return FileCredentialStore(directory / 'accounts')
    if value == {'backend': 'keyring'}:
        return KeyringCredentialStore(directory / 'accounts')
    raise ValueError('Unknown credential storage backend')

def select_store(backend: str, directory: Path | None = None) -> FileCredentialStore:
    directory = directory or auth_directory()
    if backend not in {'file', 'keyring'}:
        raise ValueError('Unknown credential storage backend')
    FileCredentialStore(directory)._prepare()
    store = FileCredentialStore(directory / 'accounts') if backend == 'file' else KeyringCredentialStore(directory / 'accounts')
    store._prepare()
    choice = directory / 'storage.json'
    if (choice.exists() or choice.is_symlink()) and read_private_json(choice) != {'backend': backend}:
        raise ValueError('Credential backend already selected; keep it to preserve existing accounts')
    fd = os.open(choice, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as out:
        json.dump({'backend': backend}, out)
    return store
