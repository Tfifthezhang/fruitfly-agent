"""Explicit unrestricted execution strategy for externally isolated runtimes."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
from typing import AsyncIterator, Mapping

from fruitfly_agent.core.tool_runtime.authorization import AuthorizationDecision, AuthorizationRequest
from .permissions import PermissionPolicy


class UnrestrictedExecutionPolicy(PermissionPolicy):
    """Retain the installed backend and let its external environment bound effects."""

    @staticmethod
    def prepare_environment(environment: Mapping[str, str]) -> dict[str, str]:
        return dict(environment)

    def bind(self, config, *, confirm, audit=None, process_environment=None):
        return replace(config, tool_authorizer=UnrestrictedAuthorizer(audit=audit))

    def identity(self) -> dict:
        return {"implementation": "unrestricted-execution-v1", "workspace": str(self.workspace),
                "mode": "unrestricted", "filesystem": "unrestricted", "local_execution": "allow",
                "network_reads": "allow", "environment": "inherited"}


class UnrestrictedAuthorizer:
    def __init__(self, *, audit=None):
        self.audit = audit

    @asynccontextmanager
    async def authorize(self, request: AuthorizationRequest, *, signal: asyncio.Event | None = None
                        ) -> AsyncIterator[AuthorizationDecision]:
        if signal is not None and signal.is_set():
            raise asyncio.CancelledError
        try:
            yield AuthorizationDecision(True, "host selected unrestricted execution")
        finally:
            if self.audit is not None:
                self.audit({"call_id": request.call_id, "tool": request.tool_name,
                            "operation": request.permission.operation if request.permission else "unknown",
                            "allowed": True, "reason": "host selected unrestricted execution"})


__all__ = ["UnrestrictedExecutionPolicy"]
