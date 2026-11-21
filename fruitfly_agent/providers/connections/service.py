"""Explicit account operations and stale-while-refresh model directories."""
from __future__ import annotations
import json
import os
from pathlib import Path
import secrets
import threading
import time
from typing import Any
from uuid import uuid4
import httpx
from .registry import ConnectionRegistry, builtin_connections
from .catalog import CatalogCache, CatalogScope, CatalogSnapshot
from ..auth.stores import auth_directory, configured_store, select_store, read_private_json
from ..auth.session import AuthSession, binding_identity
from ..auth.oauth import OAuthAttempt
from fruitfly_agent.core.errors import FatalError

class ConnectionService:
    def __init__(self, *, directory: Path | None = None, cache_directory: Path | None = None,
                 store: Any = None, registry: ConnectionRegistry | None = None):
        self.directory = directory or auth_directory()
        self.cache = CatalogCache(cache_directory or Path(os.environ.get('XDG_CACHE_HOME', str(Path.home() / '.cache'))) / 'fruitfly-agent/models')
        self.store = store
        self._injected_store = store is not None
        self.registry = registry or builtin_connections()
        self._lock = threading.Lock()
        self._refreshing: set[str] = set()
        self._retry_at: dict[str, float] = {}
        self._failures: dict[str, int] = {}
        self._errors: dict[str, str] = {}
        self._account_epochs: dict[str, str] = {}
        self._variable_connections: dict[str, tuple[str, str, str]] = {}

    def bind_variable(self, integration: str, name: str, environment) -> str:
        from ..auth.environment import environment_key
        from .contracts import ConnectionProfile

        connection = ConnectionProfile.from_dict({'integration': integration, 'credential': {'env': name}})
        if self.registry.get(integration).method.kind != 'key':
            raise ValueError('This connection requires account authorization')
        key = environment_key(connection.credential_env, environment)
        if not key:
            raise ValueError('Subscription key variable is missing or invalid')
        from ..auth.bindings import static_key_binding
        account = static_key_binding(self.directory / "bindings", integration, name, key)
        self._variable_connections[account] = (integration, name, key)
        return account

    def profile(self, integration: str, account: str):
        from .contracts import ConnectionProfile

        binding = self._variable_connections.get(account)
        if binding is None:
            return ConnectionProfile(integration, account=account)
        if binding[0] != integration:
            raise ValueError('Connection integration mismatch')
        return ConnectionProfile(integration, credential_env=binding[1])

    def clear_variable_connections(self) -> None:
        self._variable_connections.clear()

    def credentials(self) -> Any:
        if self.store is None:
            self.store = configured_store(self.directory)
        return self.store

    def choose_storage(self, backend: str) -> None:
        if not self._injected_store:
            self.store = select_store(backend, self.directory)

    def accounts(self) -> tuple[dict[str, str], ...]:
        try:
            return self.credentials().list()
        except ValueError:
            return ()

    def ready(self, integration: str, account: str) -> bool:
        if account in self._variable_connections:
            return self._variable_connections[account][0] == integration
        try:
            record = self.credentials().read(account)
            return bool(record and record.get('integration') == integration and record.get('status') == 'connected')
        except (OSError, ValueError):
            return False

    def connect_key(self, integration: str, key: str, label: str, account: str = '') -> str:
        definition = self.registry.get(integration)
        if definition.method.kind != 'key' or not key or any(ord(c) < 33 for c in key):
            raise ValueError('Enter a nonempty subscription key without whitespace')
        if account:
            previous = self.credentials().read(account)
            if not previous or previous.get('integration') != integration:
                raise ValueError('Account integration mismatch')
        account = account or uuid4().hex
        record = {'integration': integration, 'account': account, 'label': label or definition.label,
            'status': 'connected', 'access_token': key, 'binding_secret': secrets.token_hex(32)}
        record['binding'] = binding_identity(record)
        self.credentials().modify(account, lambda _: record)
        self._account_epochs[account] = record['binding']
        return account

    def begin_login(self, integration: str, account: str = '') -> tuple[OAuthAttempt, str, dict[str, Any]]:
        definition = self.registry.get(integration)
        if definition.begin_login is None:
            raise ValueError('Connection does not use browser authorization')
        saved = self.credentials().read(account) if account else None
        if saved and saved.get('integration') != integration:
            raise ValueError('Account integration mismatch')
        # Host identity is separate from account credentials and stable across restarts.
        host_path = self.directory / 'host.json'
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            fd = os.open(host_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            if host_path.is_symlink():
                raise ValueError('Host identity must not be a symlink')
        else:
            with os.fdopen(fd, 'w') as out:
                json.dump({'id': 'urn:uuid:' + str(uuid4())}, out)
        host_id = read_private_json(host_path)['id']
        record = saved or {'account': uuid4().hex, 'integration': integration,
            'binding_secret': secrets.token_hex(32), 'label': ''}
        if record.get('status') != 'connected':
            record = {**record, 'binding_secret': secrets.token_hex(32)}
        attempt, url = definition.begin_login(host_id, record)
        return attempt, url, record

    def complete_login(self, attempt: OAuthAttempt, record: dict[str, Any]) -> str:
        definition = self.registry.get(record['integration'])
        try:
            result = definition.complete_login(attempt, record)
            self.credentials().modify(result['account'], lambda _: result)
            self._account_epochs[result['account']] = result['binding']
            return str(result['account'])
        finally:
            attempt.close()

    def logout(self, account: str) -> bool:
        record = self.credentials().read(account)
        if not record:
            return True
        revoke = self.registry.get(record['integration']).revoke
        confirmed = revoke(record) if revoke and record.get('refresh_token') else False
        def clear(current: dict[str, Any] | None) -> dict[str, Any]:
            if current is None:
                return {'account': account, 'status': 'signed_out'}
            return {k: v for k, v in {**current, 'status': 'signed_out'}.items()
                    if k not in {'access_token', 'refresh_token', 'id_token'}}
        self.credentials().modify(account, clear)
        return confirmed

    def rename(self, account: str, label: str) -> None:
        if not label.strip() or any(ord(c) < 32 for c in label):
            raise ValueError('Account label must be nonempty text')
        self.credentials().modify(account, lambda value: {**(value or {}), 'account': account, 'label': label})

    def scope(self, integration: str, account: str) -> CatalogScope:
        definition = self.registry.get(integration)
        if account in self._variable_connections:
            return CatalogScope(integration, definition.endpoint, account)
        if account not in self._account_epochs:
            record = self.credentials().read(account)
            self._account_epochs[account] = str((record or {}).get('binding', ''))
        return CatalogScope(integration, definition.endpoint, account + ':' + self._account_epochs[account])

    def snapshot(self, integration: str, account: str, *, refresh_stale: bool = False) -> CatalogSnapshot | None:
        scope = self.scope(integration, account)
        snapshot = self.cache.read(scope)
        if refresh_stale and (snapshot is None or snapshot.stale(time.time())):
            self.refresh(integration, account)
        return snapshot

    def state(self, integration: str, account: str) -> str:
        key = self.scope(integration, account).key()
        with self._lock:
            return 'Refreshing models…' if key in self._refreshing else self._errors.get(key, '')

    def refresh(self, integration: str, account: str, *, force: bool = False) -> None:
        scope = self.scope(integration, account)
        key = scope.key()
        with self._lock:
            if key in self._refreshing or (not force and self._retry_at.get(key, 0) > time.time()):
                return
            self._refreshing.add(key)
        def work() -> None:
            try:
                self._fetch(integration, account)
                with self._lock:
                    self._errors.pop(key, None)
                    self._failures.pop(key, None)
                    self._retry_at.pop(key, None)
            except Exception:
                # Raw HTTP errors can contain tokens and callback URLs.
                with self._lock:
                    failures = self._failures.get(key, 0) + 1
                    self._failures[key] = failures
                    self._retry_at[key] = time.time() + min(3600, 30 * 2 ** min(failures, 7))
                    self._errors[key] = 'Refresh unavailable; cached models retained. Check connection or retry later.'
            finally:
                with self._lock:
                    self._refreshing.discard(key)
        threading.Thread(target=work, daemon=True).start()

    def _fetch(self, integration: str, account: str) -> None:
        definition = self.registry.get(integration)
        scope = self.scope(integration, account)
        cached = self.cache.read(scope)
        binding = self._variable_connections.get(account)
        if binding is not None:
            if binding[0] != integration:
                raise ValueError('Connection integration mismatch')
            token = binding[2]
        else:
            auth = AuthSession(self.credentials(), account, integration, definition.refresh)
            token = auth.resolve()
        headers = {'Authorization': 'Bearer ' + token, 'User-Agent': 'fruitfly-agent/0.1'}
        if cached and cached.etag:
            headers['If-None-Match'] = cached.etag
        if cached and cached.last_modified:
            headers['If-Modified-Since'] = cached.last_modified
        response = httpx.get(definition.endpoint + definition.models_path, headers=headers, timeout=8, follow_redirects=False)
        if response.status_code == 304 and cached:
            self.cache.write(scope, CatalogSnapshot(cached.models, time.time(), cached.etag, cached.last_modified), complete=True)
            return
        if response.status_code != 200:
            raise FatalError('Model directory unavailable')
        models = definition.parse_models(response.json())
        if len({row['id'] for row in models}) != len(models):
            raise ValueError('Duplicate model directory entries')
        self.cache.write(scope, CatalogSnapshot(tuple(models), time.time(), response.headers.get('etag', ''),
            response.headers.get('last-modified', '')), complete=True)
