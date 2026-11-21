"""Refresh credentials without changing stable authorization identity."""
from __future__ import annotations
import asyncio
import hashlib
import hmac
import time
from typing import Any, Callable
from .contracts import CredentialStore
from fruitfly_agent.core.errors import FatalError

class AuthSession:
    def __init__(self, store: CredentialStore, account: str, integration: str,
                 refresh: Callable[[dict[str, Any]], dict[str, Any]] | None = None):
        self.store, self.account, self.integration, self.refresh = store, account, integration, refresh
        record = self._record()
        self.identity = record['binding']
        self.label = str(record.get('label', 'Account'))

    def _record(self) -> dict[str, Any]:
        record = self.store.read(self.account)
        if not record or record.get('integration') != self.integration or record.get('status') != 'connected':
            raise FatalError('Account needs authorization', details={'kind': 'authentication_required'})
        return record

    def resolve(self) -> str:
        def update(record: dict[str, Any] | None) -> dict[str, Any]:
            if not record or record.get('status') != 'connected' or record.get('binding') != self.identity:
                raise FatalError('Account authorization changed; reconnect the model', details={'kind': 'authentication_required'})
            if record.get('expires_at', float('inf')) <= time.time() + 120:
                if self.refresh is None:
                    raise FatalError('Account needs authorization', details={'kind': 'authentication_required'})
                try:
                    record = self.refresh(record)
                except FatalError as exc:
                    if not isinstance(exc.details, dict) or exc.details.get('kind') != 'authentication_required':
                        raise
                    record = {k: v for k, v in {**record, 'status': 'authorization_required'}.items()
                              if k not in {'access_token', 'refresh_token', 'id_token'}}
            return record
        record = self._record()
        if record.get('binding') != self.identity:
            raise FatalError('Account authorization changed; reconnect the model', details={'kind': 'authentication_required'})
        if record.get('expires_at', float('inf')) <= time.time() + 120:
            record = self.store.modify(self.account, update)
        if record.get('status') != 'connected':
            raise FatalError('Account needs authorization', details={'kind': 'authentication_required'})
        return str(record['access_token'])

    async def token(self, signal: asyncio.Event | None = None) -> str:
        if signal is not None and signal.is_set():
            raise asyncio.CancelledError
        # The bounded refresh persists rotating credentials even if its caller cancels.
        from fruitfly_agent.core.context.tasks import bounded_call
        result = await bounded_call(asyncio.to_thread(self.resolve), timeout=45, signal=signal)
        if signal is not None and signal.is_set():
            raise asyncio.CancelledError
        return result

def binding_identity(record: dict[str, Any]) -> str:
    identity = '|'.join(str(record.get(k, '')) for k in ('integration', 'subject', 'client_id', 'account'))
    return hmac.new(record['binding_secret'].encode(), identity.encode(), hashlib.sha256).hexdigest()
