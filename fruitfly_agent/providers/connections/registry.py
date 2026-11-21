"""Connection discovery and offline model resolution through one owning registry."""
from __future__ import annotations
from typing import Any
from .contracts import ConnectionDefinition, ConnectionProfile

class ConnectionRegistry:
    def __init__(self) -> None:
        self._definitions: dict[str, ConnectionDefinition] = {}

    def register(self, definition: ConnectionDefinition) -> None:
        if definition.id in self._definitions:
            raise ValueError('Duplicate connection integration')
        self._definitions[definition.id] = definition

    def get(self, integration: str) -> ConnectionDefinition:
        try:
            return self._definitions[integration]
        except KeyError:
            raise ValueError('Unsupported connection integration: ' + integration) from None

    def definitions(self) -> tuple[ConnectionDefinition, ...]:
        return tuple(self._definitions.values())

    def resolve(self, connection: ConnectionProfile, entry: dict[str, Any]) -> dict[str, Any]:
        definition = self.get(connection.integration)
        if connection.credential_env and definition.method.kind != 'key':
            raise ValueError('This subscription requires a renewable account authorization')
        forbidden = entry.keys() & {'api_key_env'}
        if forbidden:
            raise ValueError('Connected models cannot contain API key variables')
        resolved = {'sdk': definition.sdk, 'protocol': definition.protocol, 'service': definition.service,
                    'base_url': definition.endpoint}
        if any(name in entry and entry[name] != value for name, value in resolved.items()):
            raise ValueError('Connected model route differs from its registered integration')
        return {**entry, **resolved, 'access': connection.to_dict(), 'api_key_env': ''}

_EXTENSIONS: dict[str, ConnectionDefinition] = {}

def register_connection(definition: ConnectionDefinition) -> None:
    if definition.id in {item.id for item in builtin_connections().definitions()}:
        raise ValueError('Connection ID is already registered')
    _EXTENSIONS[definition.id] = definition

def builtin_connections() -> ConnectionRegistry:
    from .methods.opencode_go import definition as go_definition
    from .methods.chatgpt import definition as chatgpt_definition
    registry = ConnectionRegistry()
    registry.register(go_definition())
    registry.register(chatgpt_definition())
    for definition in _EXTENSIONS.values():
        registry.register(definition)
    return registry
