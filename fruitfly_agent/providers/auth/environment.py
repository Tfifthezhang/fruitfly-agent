"""Supply static subscription authorization from an explicit secret variable."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Mapping

from fruitfly_agent.core.errors import FatalError


def environment_key(name: str, environment: Mapping[str, str]) -> str:
    key = environment.get(name, '')
    return key if key and all(33 <= ord(char) < 127 for char in key) else ''


class EnvironmentAuthorization:
    def __init__(self, integration: str, name: str, environment: Mapping[str, str],
                 *, binding_directory: Path | None = None):
        self.integration = integration
        self.account = name
        self.label = name
        self._key = environment_key(name, environment)
        if not self._key:
            raise FatalError(f'Subscription credential unavailable: {name}',
                             details={'kind': 'authentication_required'})
        from .bindings import static_key_binding
        from .stores import auth_directory

        self.identity = static_key_binding(binding_directory or auth_directory() / 'bindings',
                                           integration, name, self._key)

    async def token(self, signal: asyncio.Event | None = None) -> str:
        if signal is not None and signal.is_set():
            raise asyncio.CancelledError
        return self._key
