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
        self._factories: dict[tuple[str, str], ProviderFactory] = {}

    def register(self, sdk: str, protocol: str, factory: ProviderFactory) -> None:
        if not sdk or not protocol or not callable(factory):
            raise ValueError('registration requires SDK, protocol and a factory')
        self._factories[sdk, protocol] = factory

    def registered_pairs(self) -> tuple[tuple[str, str], ...]:
        """Read-only setup metadata; never invokes factories or SDK clients."""
        return tuple(self._factories)

    def validate(self, spec: ModelSpec) -> None:
        if (spec.provider.sdk, spec.provider.protocol) not in self._factories:
            raise ValueError(f"unregistered SDK/protocol combination: {spec.provider.sdk}/{spec.provider.protocol}")

    def create(self, spec: ModelSpec, env: Mapping[str, str] | None = None) -> Provider:
        self.validate(spec)
        factory = self._factories[spec.provider.sdk, spec.provider.protocol]
        source = env if env is not None else os.environ
        api_key = source.get(spec.provider.api_key_env, "")
        if not api_key:
            raise ValueError(f"missing API key: {spec.provider.api_key_env}")
        return factory(spec, api_key)


def load_model_specs(path: str | Path) -> dict[str, ModelSpec]:
    class CatalogLoader(yaml.SafeLoader):
        pass
    def unique_mapping(loader, node):
        result = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node)
            if not isinstance(key, str) or key in result:
                raise ValueError('model catalog requires distinct string keys')
            result[key] = loader.construct_object(value_node)
        return result
    CatalogLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)
    try:
        raw = yaml.load(Path(path).read_text(encoding="utf-8"), Loader=CatalogLoader) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid model catalog YAML: {path}") from exc
    if not isinstance(raw, dict):
        raise ValueError("model catalog must be a mapping")
    if raw.keys() - {'models', 'metadata'}:
        raise ValueError('model catalog accepts only models and optional metadata')
    if 'metadata' in raw:
        from .request_options import json_mapping
        json_mapping(raw['metadata'], 'model catalog metadata')
    models = raw.get("models")
    if not isinstance(models, dict):
        raise ValueError("model catalog must contain a 'models' mapping")
    result = {}
    for name, value in models.items():
        try:
            if not isinstance(value, dict) or not isinstance(value.get("sdk"), str) or not isinstance(value.get("protocol"), str):
                raise ValueError("sdk and protocol must name the client library and API format")
            result[str(name)] = ModelSpec.from_dict(str(name), value)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid model specification {name!r}: {exc}") from exc
    return result


def default_registry() -> ProviderRegistry:
    from .anthropic import AnthropicProvider
    from .openai import OpenAIProvider
    from .chat_completions import ChatCompletionsProvider

    registry = ProviderRegistry()
    registry.register(
        "anthropic", "messages",
        lambda spec, key: AnthropicProvider(
            api_key=key,
            model=spec.model,
            base_url=spec.provider.base_url,
            max_tokens=spec.max_output_tokens,
            service=spec.service,
            **spec.transport,
            **spec.parameters,
        ),
    )
    registry.register(
        "openai", "responses",
        lambda spec, key: OpenAIProvider(
            api_key=key,
            model=spec.model,
            base_url=spec.provider.base_url,
            max_output_tokens=spec.max_output_tokens,
            parallel_tool_calls=spec.capabilities.parallel_tool_calls,
            service=spec.service,
            **spec.transport,
            **spec.parameters,
        ),
    )
    registry.register('openai', 'chat-completions', lambda spec, key: ChatCompletionsProvider(
        api_key=key, model=spec.model, base_url=spec.provider.base_url,
        max_output_tokens=spec.max_output_tokens, service=spec.service,
        parallel_tool_calls=spec.capabilities.parallel_tool_calls,
        **spec.transport, **spec.parameters))
    return registry


__all__ = ["ProviderRegistry", "ProviderFactory", "load_model_specs", "default_registry"]
