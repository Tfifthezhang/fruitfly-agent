"""Stable values and protocols for the three-stage context pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Awaitable, Mapping, Protocol, Sequence, runtime_checkable

from ..data_model import AgentMessage, ContextDecision, ContextSnapshot
from ..mechanisms import ContextPhase

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


@dataclass(frozen=True)
class ContextProvenance:
    stage_id: str
    phase: ContextPhase
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class ContextFrame:
    system_prompt: str
    messages: tuple[AgentMessage, ...]
    tools: tuple[Any, ...]
    model: str
    max_tokens: int
    provenance: tuple[ContextProvenance, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "messages", tuple(self.messages))
        object.__setattr__(self, "tools", tuple(self.tools))
        object.__setattr__(self, "provenance", tuple(self.provenance))


@dataclass(frozen=True)
class ContextTransform:
    frame: ContextFrame
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", dict(self.metadata))


@runtime_checkable
class ContextTransformer(Protocol):
    def transform(
        self, frame: ContextFrame
    ) -> ContextTransform | ContextFrame | None | Awaitable[ContextTransform | ContextFrame | None]: ...


@runtime_checkable
class ContextReducer(Protocol):
    def estimate(self, snapshot: ContextSnapshot) -> int: ...
    async def check_budget(self, snapshot: ContextSnapshot) -> ContextDecision | None: ...
    async def react_to_overflow(
        self, snapshot: ContextSnapshot, error: Exception
    ) -> ContextDecision | None: ...


@dataclass(frozen=True)
class ContextStage:
    stage_id: str
    phase: ContextPhase
    mechanism: ContextTransformer | ContextReducer
    order: int = 100

    def __post_init__(self) -> None:
        if self.phase not in {"augmentation", "externalization", "reduction"}:
            raise ValueError(f"unsupported context stage phase: {self.phase!r}")
        if not _ID.fullmatch(self.stage_id):
            raise ValueError("context stage id must be a stable identifier")
        if isinstance(self.order, bool) or not isinstance(self.order, int):
            raise ValueError("context stage order must be an integer")
        if self.phase == "reduction":
            if not isinstance(self.mechanism, ContextReducer):
                raise TypeError("reduction stage must implement ContextReducer")
        elif not isinstance(self.mechanism, ContextTransformer):
            raise TypeError("prepare stage must implement ContextTransformer")


@dataclass(frozen=True)
class ContextPipelineProfile:
    augmentation: tuple[str, ...] = ()
    externalization: tuple[str, ...] = ()
    reduction: tuple[str, ...] = ()

    @classmethod
    def from_stages(cls, stages: Sequence[ContextStage]) -> "ContextPipelineProfile":
        grouped: dict[ContextPhase, list[str]] = {
            "augmentation": [], "externalization": [], "reduction": []
        }
        for stage in stages:
            grouped[stage.phase].append(stage.stage_id)
        return cls(**{key: tuple(value) for key, value in grouped.items()})

    def to_dict(self) -> dict[str, Any]:
        return {
            "augmentation": list(self.augmentation),
            "externalization": list(self.externalization),
            "reduction": list(self.reduction),
        }


__all__ = [
    "ContextPhase", "ContextProvenance", "ContextFrame", "ContextTransform",
    "ContextTransformer", "ContextReducer", "ContextStage", "ContextPipelineProfile",
]
