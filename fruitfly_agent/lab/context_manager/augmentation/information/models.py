"""Vendor-neutral data envelopes for composable information spaces."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

InformationEffectTarget = Literal["system_prompt", "messages", "tool"]


def _required(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


@dataclass(frozen=True)
class InformationDescriptor:
    mechanism_id: str
    source_types: frozenset[str] = field(default_factory=frozenset)
    representations: frozenset[str] = field(default_factory=lambda: frozenset({"text"}))
    capabilities: frozenset[str] = field(default_factory=frozenset)
    deterministic: bool = True
    uses_network: bool = False
    uses_provider: bool = False

    def __post_init__(self) -> None:
        _required(self.mechanism_id, "mechanism_id")


@dataclass(frozen=True)
class InformationSpaceDescriptor:
    space_id: str
    label: str = ""
    scope: str = "workspace"
    external: bool = False
    persistent: bool = False
    writable: bool = False

    def __post_init__(self) -> None:
        _required(self.space_id, "space_id")
        _required(self.scope, "scope")


@dataclass(frozen=True, order=True)
class InformationRef:
    space_id: str
    artifact_id: str

    def __post_init__(self) -> None:
        _required(self.space_id, "space_id")
        _required(self.artifact_id, "artifact_id")

    def to_dict(self) -> dict[str, str]:
        return {"space_id": self.space_id, "artifact_id": self.artifact_id}


@dataclass(frozen=True)
class InformationArtifact:
    ref: InformationRef
    payload: Any
    representation: str = "text"
    media_type: str = "text/plain"
    provenance: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    updated_at: float = 0.0
    valid_from: float | None = None
    valid_until: float | None = None
    confidence: float = 1.0
    trust: float = 1.0
    sensitive: bool = False

    def __post_init__(self) -> None:
        _required(self.representation, "representation")
        _required(self.media_type, "media_type")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if not 0.0 <= self.trust <= 1.0:
            raise ValueError("trust must be between 0 and 1")

    @property
    def text(self) -> str:
        if isinstance(self.payload, str):
            return self.payload
        if isinstance(self.payload, (dict, list, tuple)):
            return json.dumps(self.payload, ensure_ascii=False, sort_keys=True, default=str)
        return str(self.payload)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref": self.ref.to_dict(),
            "payload": self.payload,
            "text": self.text,
            "representation": self.representation,
            "media_type": self.media_type,
            "provenance": dict(self.provenance),
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "confidence": self.confidence,
            "trust": self.trust,
            "sensitive": self.sensitive,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "InformationArtifact":
        raw_ref = value.get("ref")
        if not isinstance(raw_ref, Mapping):
            raise ValueError("information artifact ref must be an object")
        return cls(
            ref=InformationRef(
                space_id=str(raw_ref.get("space_id") or ""),
                artifact_id=str(raw_ref.get("artifact_id") or ""),
            ),
            payload=value.get("payload", value.get("text", "")),
            representation=str(value.get("representation") or "text"),
            media_type=str(value.get("media_type") or "text/plain"),
            provenance=dict(value.get("provenance") or {}),
            metadata=dict(value.get("metadata") or {}),
            created_at=float(value.get("created_at") or 0.0),
            updated_at=float(value.get("updated_at") or 0.0),
            valid_from=(
                float(value["valid_from"]) if value.get("valid_from") is not None else None
            ),
            valid_until=(
                float(value["valid_until"]) if value.get("valid_until") is not None else None
            ),
            confidence=float(value.get("confidence", 1.0)),
            trust=float(value.get("trust", 1.0)),
            sensitive=bool(value.get("sensitive", False)),
        )


@dataclass(frozen=True)
class InformationQuery:
    text: str
    scope: str = "workspace"
    space_ids: tuple[str, ...] = ()
    top_k: int = 5
    max_chars: int = 4_000
    filters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _required(self.text, "text")
        _required(self.scope, "scope")
        if isinstance(self.top_k, bool) or self.top_k < 1:
            raise ValueError("top_k must be at least 1")
        if isinstance(self.max_chars, bool) or self.max_chars < 1:
            raise ValueError("max_chars must be at least 1")


@dataclass(frozen=True)
class InformationHit:
    artifact: InformationArtifact
    score: float
    scores: Mapping[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact": self.artifact.to_dict(),
            "score": self.score,
            "scores": dict(self.scores),
        }


@dataclass(frozen=True)
class InformationAccessError:
    space_id: str
    operation: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "space_id": self.space_id,
            "operation": self.operation,
            "message": self.message,
        }


@dataclass(frozen=True)
class InformationSearchResult:
    hits: tuple[InformationHit, ...] = ()
    errors: tuple[InformationAccessError, ...] = ()


@dataclass(frozen=True)
class InformationEffect:
    target: InformationEffectTarget
    content: str
    refs: tuple[InformationRef, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.target not in ("system_prompt", "messages", "tool"):
            raise ValueError(f"unsupported information effect target: {self.target}")
        _required(self.content, "content")


__all__ = [
    "InformationEffectTarget",
    "InformationDescriptor",
    "InformationSpaceDescriptor",
    "InformationRef",
    "InformationArtifact",
    "InformationQuery",
    "InformationHit",
    "InformationAccessError",
    "InformationSearchResult",
    "InformationEffect",
]
