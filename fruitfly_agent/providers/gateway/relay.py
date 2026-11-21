"""Validate and forward model requests without exporting upstream credentials."""
from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import hashlib
import asyncio
import json
import secrets
import time
from typing import Any, AsyncIterator, Callable
from urllib.parse import urlsplit

import httpx

from ..auth.contracts import ModelAuthorization

_ROUTES = frozenset({'/responses', '/chat/completions'})


class RelayRejected(ValueError):
    """A request fell outside the grant or relay limits."""


@dataclass(frozen=True)
class RelayGrant:
    model: str
    endpoint: str
    route: str
    authorization: ModelAuthorization = field(repr=False)
    expires_at: float = 0.0
    prepare_headers: Callable[[str], dict[str, str]] | None = field(default=None, repr=False)
    validate_request: Callable[[dict[str, Any]], None] | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        url = urlsplit(self.endpoint)
        if (self.route not in _ROUTES or url.scheme != 'https' or not url.hostname
                or url.username or url.password or url.query or url.fragment or not self.model):
            raise ValueError('Invalid model relay route')


class ModelRelay:
    """Own opaque grants. The caller owns the client and its transport lifecycle."""

    def __init__(self, upstream: httpx.AsyncClient, *, max_request_bytes: int = 16 * 1024 * 1024):
        self._upstream = upstream
        self._grants: dict[bytes, RelayGrant] = {}
        self._max_request_bytes = max_request_bytes
        self._active: dict[bytes, set[asyncio.Task[Any]]] = {}

    @staticmethod
    def _digest(token: str) -> bytes:
        return hashlib.sha256(token.encode()).digest()

    def issue(self, grant: RelayGrant) -> str:
        if not time.monotonic() < grant.expires_at < float('inf'):
            raise ValueError('A relay grant needs a finite future expiration')
        token = secrets.token_urlsafe(32)
        self._grants[self._digest(token)] = grant
        return token

    def revoke(self, token: str) -> None:
        self._grants.pop(self._digest(token), None)
        for task in tuple(self._active.get(self._digest(token), ())):
            task.cancel()

    def _grant(self, token: str) -> RelayGrant:
        grant = self._grants.get(self._digest(token))
        if grant is None or grant.expires_at <= time.monotonic():
            raise RelayRejected('Model relay authorization is unavailable')
        return grant

    @asynccontextmanager
    async def stream(self, token: str, route: str, body: bytes,
                     *, conversation: str = '') -> AsyncIterator[httpx.Response]:
        grant = self._grant(token)
        if route != grant.route or len(body) > self._max_request_bytes:
            raise RelayRejected('Model relay route or request size is outside the grant')
        try:
            request = json.loads(body)
        except (UnicodeDecodeError, ValueError) as exc:
            raise RelayRejected('Invalid model request JSON') from exc
        if not isinstance(request, dict) or request.get('model') != grant.model or request.get('stream') is not True:
            raise RelayRejected('Model relay requires the granted model and streaming')
        if len(conversation) > 128 or any(not (char.isascii() and (char.isalnum() or char in '-_.')) for char in conversation):
            raise RelayRejected('Invalid model relay conversation identifier')
        if grant.validate_request is not None:
            grant.validate_request(request)
        try:
            encoded = json.dumps(request, allow_nan=False).encode()
        except (ValueError, RecursionError) as exc:
            raise RelayRejected('Invalid model request values') from exc
        access = await grant.authorization.token()
        if self._grant(token) is not grant:
            raise RelayRejected('Model relay authorization changed')
        headers = {**(grant.prepare_headers(conversation) if grant.prepare_headers else {}),
                   'Authorization': 'Bearer ' + access, 'User-Agent': 'fruitfly-agent/0.1',
                   'Content-Type': 'application/json', 'Accept': 'text/event-stream'}
        task = asyncio.current_task()
        assert task is not None
        active = self._active.setdefault(self._digest(token), set())
        active.add(task)
        try:
            async with self._upstream.stream('POST', grant.endpoint.rstrip('/') + route, content=encoded,
                                             headers=headers, follow_redirects=False) as response:
                yield response
        finally:
            active.discard(task)
            if not active:
                self._active.pop(self._digest(token), None)
