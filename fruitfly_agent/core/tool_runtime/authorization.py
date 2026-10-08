"""Execution-scoped authorization contracts; policy and interaction live outside Core."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncContextManager, AsyncIterator, Protocol

@dataclass(frozen=True)
class ToolPermission:
    operation: str
    path_arguments: tuple[str, ...] = ()

@dataclass(frozen=True)
class AuthorizationRequest:
    call_id: str
    tool_name: str
    arguments: dict[str, Any]
    permission: ToolPermission | None

@dataclass(frozen=True)
class AuthorizationDecision:
    allowed: bool
    reason: str = ""

@dataclass(frozen=True)
class AuthorizationPrompt:
    request_id: str
    tool_name: str
    operation: str
    targets: tuple[str, ...]
    summary: str
    session_label: str
    session_targets: tuple[str, ...] = ()

class ToolAuthorizer(Protocol):
    def authorize(self, request: AuthorizationRequest, *, signal: asyncio.Event | None = None
                  ) -> AsyncContextManager[AuthorizationDecision]: ...

@asynccontextmanager
async def unrestricted_authorization() -> AsyncIterator[AuthorizationDecision]:
    """Compatibility for direct Core callers that have not supplied a policy."""
    yield AuthorizationDecision(True)

__all__ = ["ToolPermission", "AuthorizationRequest", "AuthorizationDecision", "AuthorizationPrompt", "ToolAuthorizer"]
