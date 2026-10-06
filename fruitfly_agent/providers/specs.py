"""Immutable descriptions of model endpoints used in reproducible runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ModelCapabilities:
    tools: bool = True
    parallel_tool_calls: bool = False
    vision: bool = False
    reasoning: bool = False
    streaming: bool = True


@dataclass(frozen=True)
class ProviderSpec:
    type: str
    api_key_env: str
    base_url: str | None = None


@dataclass(frozen=True)
class ModelSpec:
    id: str
    provider: ProviderSpec
    model: str
    context_window: int
    max_output_tokens: int = 4096
    capabilities: ModelCapabilities = field(default_factory=ModelCapabilities)
    parameters: dict[str, Any] = field(default_factory=dict)

    def require(
        self, *, tools: bool = False, vision: bool = False, streaming: bool = True
    ) -> None:
        required = {"tools": tools, "vision": vision, "streaming": streaming}
        missing = [name for name, needed in required.items() if needed and not getattr(self.capabilities, name)]
        if missing:
            raise ValueError(f"model {self.id!r} lacks required capabilities: {', '.join(missing)}")

    @classmethod
    def from_dict(cls, model_id: str, raw: dict[str, Any]) -> "ModelSpec":
        caps = raw.get("capabilities") or {}
        return cls(
            id=model_id,
            provider=ProviderSpec(
                type=str(raw["provider"]),
                api_key_env=str(raw.get("api_key_env") or _default_key_env(str(raw["provider"]))),
                base_url=raw.get("base_url"),
            ),
            model=str(raw["model"]),
            context_window=int(raw["context_window"]),
            max_output_tokens=int(raw.get("max_output_tokens", 4096)),
            capabilities=ModelCapabilities(**caps),
            parameters=dict(raw.get("parameters") or {}),
        )


def _default_key_env(provider: str) -> str:
    return f"{provider.upper()}_API_KEY"


__all__ = ["ModelCapabilities", "ProviderSpec", "ModelSpec"]
