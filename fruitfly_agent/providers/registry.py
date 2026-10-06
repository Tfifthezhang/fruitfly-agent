"""Provider factories and YAML model-catalog loading."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Mapping

import yaml

from fruitfly_agent.core.extensions.protocols import Provider

from .specs import ModelSpec

ProviderFactory = Callable[[ModelSpec, str], Provider]


class ProviderRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, ProviderFactory] = {}

    def register(self, name: str, factory: ProviderFactory) -> None:
        self._factories[name] = factory

    def create(self, spec: ModelSpec, env: Mapping[str, str] | None = None) -> Provider:
        factory = self._factories.get(spec.provider.type)
        if factory is None:
            raise ValueError(f"unknown provider type: {spec.provider.type!r}")
        source = env if env is not None else os.environ
        api_key = source.get(spec.provider.api_key_env, "")
        if not api_key:
            raise ValueError(f"missing API key: {spec.provider.api_key_env}")
        return factory(spec, api_key)


def load_model_specs(path: str | Path) -> dict[str, ModelSpec]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    models = raw.get("models")
    if not isinstance(models, dict):
        raise ValueError("model catalog must contain a 'models' mapping")
    return {str(name): ModelSpec.from_dict(str(name), value) for name, value in models.items()}


def default_registry() -> ProviderRegistry:
    from .anthropic import AnthropicProvider
    from .openai import OpenAIProvider

    registry = ProviderRegistry()
    registry.register(
        "anthropic",
        lambda spec, key: AnthropicProvider(
            api_key=key,
            model=spec.model,
            base_url=spec.provider.base_url,
            max_tokens=spec.max_output_tokens,
            **spec.parameters,
        ),
    )
    registry.register(
        "openai",
        lambda spec, key: OpenAIProvider(
            api_key=key,
            model=spec.model,
            base_url=spec.provider.base_url,
            max_output_tokens=spec.max_output_tokens,
            parallel_tool_calls=spec.capabilities.parallel_tool_calls,
            **spec.parameters,
        ),
    )
    return registry


__all__ = ["ProviderRegistry", "ProviderFactory", "load_model_specs", "default_registry"]
