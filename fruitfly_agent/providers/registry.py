"""Provider factories and YAML model-catalog loading."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Mapping

import yaml
import httpx

from .auth.contracts import ModelAuthorization

from fruitfly_agent.core.extensions.protocols import Provider

from .specs import ModelSpec

ProviderFactory = Callable[[ModelSpec, str], Provider]


class ProviderRegistry:
    def __init__(self, *, credential_store=None, binding_directory: Path | None = None,
                 authorization_factory: Callable[[ModelSpec], ModelAuthorization] | None = None) -> None:
        self.authorization_factory = authorization_factory
        self.credential_store = credential_store
        self.binding_directory = binding_directory
        self._factories: dict[tuple[str, str], ProviderFactory] = {}
        self._default_sdks: dict[str, str] = {}

    def register(self, sdk: str, protocol: str, factory: ProviderFactory, *, default: bool = False) -> None:
        if not sdk or not protocol or not callable(factory):
            raise ValueError('registration requires SDK, protocol and a factory')
        self._factories[sdk, protocol] = factory
        if default:
            self._default_sdks[protocol] = sdk

    def sdk_for(self, protocol: str) -> str:
        """Resolve setup's SDK without constructing a client or guessing between adapters."""
        if protocol in self._default_sdks:
            return self._default_sdks[protocol]
        choices = tuple(sdk for sdk, api in self._factories if api == protocol)
        if len(choices) != 1:
            raise ValueError(f'protocol {protocol!r} requires one registered SDK or an explicit default adapter')
        return choices[0]

    def registered_pairs(self) -> tuple[tuple[str, str], ...]:
        """Read-only setup metadata; never invokes factories or SDK clients."""
        return tuple(self._factories)

    def validate(self, spec: ModelSpec) -> None:
        if (spec.provider.sdk, spec.provider.protocol) not in self._factories:
            raise ValueError(f"unregistered SDK/protocol combination: {spec.provider.sdk}/{spec.provider.protocol}")

    def create(self, spec: ModelSpec, env: Mapping[str, str] | None = None) -> Provider:
        self.validate(spec)
        factory = self._factories[spec.provider.sdk, spec.provider.protocol]
        if spec.access:
            from .connections.registry import builtin_connections
            from .connections.runtime import ConnectedProvider
            definition = builtin_connections().get(spec.access['integration'])
            from .connections.contracts import ConnectionProfile
            connection = ConnectionProfile.from_dict(spec.access)
            from .auth.contracts import ModelAuthorization
            auth: ModelAuthorization
            if self.authorization_factory is not None:
                auth = self.authorization_factory(spec)
            else:
                from .connections.runtime import model_authorization
                auth = model_authorization(spec, env if env is not None else os.environ,
                    credential_store=self.credential_store, binding_directory=self.binding_directory)
            validator = getattr(definition.request_policy, 'validate', None)
            if validator is not None:
                validator(spec.parameters)
            provider: Any = factory(spec, 'account-authentication-managed')
            connected = ConnectedProvider(provider, auth, output_enforced=definition.output_enforced,
                                          output_reserve=spec.output_reserve or spec.max_output_tokens)
            provider.configure_connection(auth.identity, definition.request_policy, connected.session_id)
            return connected
        source = env if env is not None else os.environ
        api_key = source.get(spec.provider.api_key_env, "")
        if not api_key:
            raise ValueError(f"missing API key: {spec.provider.api_key_env}")
        return factory(spec, api_key)


def _load_model_file(path: str | Path) -> dict[str, ModelSpec]:
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
    if raw.keys() - {'models', 'metadata', 'connections'}:
        raise ValueError('model catalog accepts only models, connections and optional metadata')
    if 'metadata' in raw:
        from .request_options import json_mapping
        json_mapping(raw['metadata'], 'model catalog metadata')
    from .connections.contracts import ConnectionProfile
    from .connections.registry import builtin_connections
    connections = raw.get('connections', {})
    if not isinstance(connections, dict):
        raise ValueError('connections must be a mapping')
    connection_profiles = {name: ConnectionProfile.from_dict(value) for name, value in connections.items()}
    for connection in connection_profiles.values():
        builtin_connections().get(connection.integration)
    models = raw.get("models")
    if not isinstance(models, dict):
        raise ValueError("model catalog must contain a 'models' mapping")
    result = {}
    for name, value in models.items():
        try:
            if isinstance(value, dict) and 'connection' in value:
                value = dict(value)
                reference = value.pop('connection')
                if reference not in connection_profiles or 'access' in value:
                    raise ValueError('Unknown or conflicting model connection')
                value = builtin_connections().resolve(connection_profiles[reference], value)
            if not isinstance(value, dict) or not isinstance(value.get("sdk"), str) or not isinstance(value.get("protocol"), str):
                raise ValueError("sdk and protocol must name the client library and API format")
            result[str(name)] = ModelSpec.from_dict(str(name), value)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid model specification {name!r}: {exc}") from exc
    return result


def default_registry(*,
    http_client_factory: Callable[[ModelSpec], httpx.AsyncClient] | None = None,
    authorization_factory: Callable[[ModelSpec], ModelAuthorization] | None = None,
) -> ProviderRegistry:
    from .anthropic import AnthropicProvider
    from .openai import OpenAIProvider
    from .chat_completions import ChatCompletionsProvider

    registry = ProviderRegistry(authorization_factory=authorization_factory)
    registry.register(
        "anthropic", "messages",
        lambda spec, key: AnthropicProvider(
            api_key=key,
            model=spec.model,
            base_url=spec.provider.base_url,
            max_tokens=spec.max_output_tokens,
            service=spec.service,
            vision=spec.capabilities.vision,
            **spec.transport,
            **spec.parameters,
        ),
        default=True,
    )
    registry.register(
        "openai", "responses",
        lambda spec, key: OpenAIProvider(
            http_client=http_client_factory(spec) if http_client_factory else None,
            api_key=key,
            model=spec.model,
            base_url=spec.provider.base_url,
            max_output_tokens=spec.max_output_tokens,
            parallel_tool_calls=spec.capabilities.parallel_tool_calls,
            service=spec.service,
            vision=spec.capabilities.vision,
            **spec.transport,
            **spec.parameters,
        ),
        default=True,
    )
    registry.register('openai', 'chat-completions', lambda spec, key: ChatCompletionsProvider(
        http_client=http_client_factory(spec) if http_client_factory else None,
        api_key=key, model=spec.model, base_url=spec.provider.base_url,
        max_output_tokens=spec.max_output_tokens, service=spec.service,
        vision=spec.capabilities.vision,
        parallel_tool_calls=spec.capabilities.parallel_tool_calls,
        **spec.transport, **spec.parameters), default=True)
    return registry


__all__ = ["ProviderRegistry", "ProviderFactory", "load_model_specs", "default_registry"]


def credential_available(spec: ModelSpec, environment: Mapping[str, str]) -> bool:
    """Offline credential readiness. Expiring refreshable grants may be renewed at request time."""
    if spec.access:
        from .connections.contracts import ConnectionProfile
        connection = ConnectionProfile.from_dict(spec.access)
        if connection.credential_env:
            from .auth.environment import environment_key
            return bool(environment_key(connection.credential_env, environment))
        from .connections.service import ConnectionService
        return ConnectionService().ready(connection.integration, connection.account)
    return bool(environment.get(spec.provider.api_key_env))


def model_catalog_companions(*sources: Path) -> dict[str, bytes]:
    """Prepare explicitly declared model resources for freezing."""
    return {'subscriptions.yaml': sources[1].read_bytes()} if len(sources) > 1 else {}


def load_model_specs(path: str | Path, *companions: str | Path) -> dict[str, ModelSpec]:
    """Merge explicitly supplied catalogs into one alias namespace."""
    result: dict[str, ModelSpec] = {}
    for source in (path, *companions):
        models = _load_model_file(source)
        duplicates = result.keys() & models.keys()
        if duplicates:
            raise ValueError('Duplicate model aliases across catalogs: ' + ', '.join(sorted(duplicates)))
        result.update(models)
    return result
