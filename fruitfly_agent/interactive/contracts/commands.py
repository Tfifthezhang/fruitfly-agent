"""Frontend-neutral command envelopes and handler contracts."""
from __future__ import annotations
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol
from fruitfly_agent.interactive.contracts.events import InteractiveEvent
from fruitfly_agent.interactive.contracts.models import InteractiveStatus


@dataclass(frozen=True)
class InteractiveCommand:
    name: str
    arguments: tuple[str, ...] = ()


@dataclass(frozen=True)
class CommandResult:
    text: str = ""
    should_exit: bool = False


class CommandContext(Protocol):
    @property
    def status(self) -> InteractiveStatus: ...

    def trace(self, limit: int = 12) -> list[InteractiveEvent]: ...


CommandHandler = Callable[[InteractiveCommand, CommandContext], CommandResult]


