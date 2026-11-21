"""Secret storage and stable account registration contracts."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, ContextManager, Protocol

class CredentialStore(Protocol):
    def read(self, account: str) -> dict[str, Any] | None: ...
    def modify(self, account: str, update: Callable[[dict[str, Any] | None], dict[str, Any]]) -> dict[str, Any]: ...
    def list(self) -> tuple[dict[str, str], ...]: ...
    def lock(self, account: str) -> ContextManager[None]: ...

@dataclass(frozen=True)
class AuthBinding:
    integration: str
    account: str
    identity: str

@dataclass(frozen=True)
class AuthMethod:
    id: str
    label: str
    kind: str
    url: str = ''

class AuthInteraction(Protocol):
    def notify(self, kind: str, value: str) -> None: ...
    def cancelled(self) -> bool: ...

class AuthenticatedAdapter(Protocol):
    """Optional protocol adapters implement to participate in account connections."""
    def configure_connection(self, identity: str, policy: Any, session_id: str) -> None: ...
    def set_access_token(self, token: str) -> None: ...
    def bind_session(self, session_id: str) -> None: ...


class ModelAuthorization(Protocol):
    integration: str
    account: str
    identity: str
    label: str

    async def token(self, signal=None) -> str: ...
