"""Structural session contract shared by runtime context and public seams."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from ..data_model.context import ContextItem
from ..data_model.messages import AgentMessage


@runtime_checkable
class SessionLike(Protocol):
    """Durable transcript seam (reference implementation: Session)."""

    def append(
        self,
        type: str,
        payload: dict[str, Any],
        *,
        parent_id: int | None = None,
        entry_id: int | None = None,
        sync: bool = False,
    ) -> Any: ...

    def read_all(self) -> list[Any]: ...

    def messages(self) -> list[AgentMessage]: ...

    def canonical_messages(self) -> list[AgentMessage]: ...

    def context_items(self) -> list[ContextItem]: ...

    def close(self) -> None: ...


__all__ = ["SessionLike"]
