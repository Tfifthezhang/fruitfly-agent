"""Public preparation and authorization contracts for external tool providers."""
from __future__ import annotations
from collections.abc import Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Protocol
import asyncio

from fruitfly_agent.core.tool_runtime import AgentTool
from fruitfly_agent.core.tool_runtime.authorization import AuthorizationRequest, AuthorizationDecision, AuthorizationPrompt


@dataclass(frozen=True)
class ToolServiceInfo:
    name: str
    transport: str
    working_directory: str
    state: str
    tools: tuple[str, ...] = ()
    location: str = 'Local host'


@dataclass(frozen=True)
class ToolServiceStart:
    name: str
    command: str
    arguments: tuple[str, ...]
    working_directory: str
    environment_names: tuple[str, ...]


StartupApproval = Callable[[ToolServiceStart], Awaitable[bool]]
Confirmation = Callable[[AuthorizationPrompt, asyncio.Event | None], Awaitable[str]]


class ExternalToolPolicy(Protocol):
    def authorize(self, request: AuthorizationRequest, confirm: Confirmation,
                  signal: asyncio.Event | None = None) -> Any: ...


@dataclass(frozen=True)
class ToolProviderContext:
    workspace: Path
    secret_resolver: Callable[[str], str | None]
    approve_start: StartupApproval
    own: Callable[[Any], Any]
    write_artifact: Callable[[str], str]
    read_artifact: Callable[[str], str]


@dataclass(frozen=True)
class PreparedToolProvider:
    tools: tuple[AgentTool, ...] = ()
    resources: tuple[Any, ...] = ()
    identity: tuple[Mapping[str, Any], ...] = ()
    policies: Mapping[str, ExternalToolPolicy] = field(default_factory=dict)
    status: Callable[[], tuple[ToolServiceInfo, ...]] = lambda: ()


class ProviderToolAuthorizer:
    """Route only explicitly registered external tools; preserve the host policy."""

    def __init__(self, base, policies: Mapping[str, ExternalToolPolicy], confirm: Confirmation, *, audit=None):
        self.base, self.policies, self.confirm = base, dict(policies), confirm
        self.audit = audit

    @asynccontextmanager
    async def authorize(self, request: AuthorizationRequest, *, signal=None) -> AsyncIterator[AuthorizationDecision]:
        policy = self.policies.get(request.tool_name)
        if policy is not None:
            async with policy.authorize(request, self.confirm, signal) as decision:
                if self.audit is not None:
                    self.audit({'tool': request.tool_name, 'operation': 'external_tool', 'allowed': decision.allowed})
                yield decision
        elif self.base is not None:
            async with self.base.authorize(request, signal=signal) as decision:
                yield decision
        else:
            yield AuthorizationDecision(False, 'no host authorizer')
