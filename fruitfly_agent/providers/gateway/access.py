"""Strict task-scoped model access descriptors supplied by an execution host."""
from __future__ import annotations

from pathlib import Path
from typing import Any
import asyncio
import ssl

import httpx

from ..auth.stores import read_private_json
from ..registry import default_registry, ProviderRegistry
from ..specs import ModelSpec
from .client import RelayTransport


class TaskAuthorization:
    def __init__(self, binding: dict[str, Any]):
        self.integration = binding['integration']
        self.account = binding['account']
        self.identity = binding['identity']
        self.label = binding['label']

    async def token(self, signal: asyncio.Event | None = None) -> str:
        if signal is not None and signal.is_set():
            raise asyncio.CancelledError
        return 'task-relay-managed'


def access_registry(path: Path) -> ProviderRegistry:
    data = read_private_json(path)
    if not isinstance(data, dict) or data.keys() != {'models'} or not isinstance(data['models'], dict):
        raise ValueError('Invalid model access descriptor')
    entries = data['models']
    for name, entry in entries.items():
        if not isinstance(name, str) or not isinstance(entry, dict) or entry.keys() != {
            'spec', 'authorization', 'socket', 'grant', 'network_url', 'ca'}:
            raise ValueError('Invalid model access entry')
        spec = ModelSpec.from_dict(name, entry['spec'])
        if spec.access is None or spec.provider.protocol not in {'responses', 'chat-completions'}:
            raise ValueError('Unsupported task model access protocol')
        auth = entry['authorization']
        if not isinstance(auth, dict) or auth.keys() != {'integration', 'account', 'identity', 'label'}:
            raise ValueError('Invalid model access authorization')
        if any(not isinstance(value, str) or not value for value in auth.values()):
            raise ValueError('Invalid model access identity')
        from ..connections.contracts import ConnectionProfile
        connection = ConnectionProfile.from_dict(spec.access)
        if auth['integration'] != connection.integration or auth['account'] != (connection.account or connection.credential_env):
            raise ValueError('Task account differs from model connection')
        if not isinstance(entry['grant'], str) or not entry['grant']:
            raise ValueError('Missing task model grant')

    def selected(spec: ModelSpec) -> dict[str, Any]:
        if spec.id not in entries:
            raise ValueError('Model is outside task access')
        entry = entries[spec.id]
        original = ModelSpec.from_dict(spec.id, entry['spec'])
        from dataclasses import replace
        if spec.max_output_tokens > original.max_output_tokens or replace(spec, max_output_tokens=original.max_output_tokens) != original:
            raise ValueError('Model differs from task access')
        return entry

    def authorization(spec: ModelSpec) -> TaskAuthorization:
        return TaskAuthorization(selected(spec)['authorization'])

    def client(spec: ModelSpec) -> httpx.AsyncClient:
        if not spec.access:
            return httpx.AsyncClient()
        entry = selected(spec)
        route = '/responses' if spec.provider.protocol == 'responses' else '/chat/completions'
        tls = ssl.create_default_context(cafile=entry['ca']) if entry['network_url'] else None
        return httpx.AsyncClient(transport=RelayTransport(Path(entry['socket']),
            upstream_url=spec.provider.base_url or '', route=route, grant=entry['grant'],
            conversation_header='x-opencode-session', network_url=entry['network_url'], tls=tls))

    return default_registry(http_client_factory=client, authorization_factory=authorization)
