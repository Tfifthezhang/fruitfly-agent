"""Service/protocol metadata from one packaged table; no built-in model policies."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from importlib.resources import files
from typing import Any, Callable
from urllib.parse import urlsplit
import re

import yaml

from .request_options import json_mapping


def _accept_options(protocol: str, model: str, options: dict[str, Any]) -> None:
    """Remote services decide which model-specific options they support."""


_CONTROLS = frozenset({'prefix_bound', 'responses_store', 'parallel_control', 'input_count',
    'chat_token_field', 'chat_stream_usage', 'base_url', 'description'})
_BOOLEANS = frozenset({'prefix_bound', 'responses_store', 'parallel_control', 'chat_stream_usage', 'input_count'})


def _validate_controls(values: dict[str, Any]) -> None:
    if values.keys() - _CONTROLS:
        raise ValueError('unsupported service protocol controls')
    if any(type(values[name]) is not bool for name in _BOOLEANS & values.keys()):
        raise ValueError('service control flags must be booleans')
    if values.get('chat_token_field', 'max_tokens') not in {'max_tokens', 'max_completion_tokens'}:
        raise ValueError('unsupported Chat output-limit parameter')
    url = values.get('base_url')
    if url is not None:
        if not isinstance(url, str):
            raise ValueError('service base_url must be HTTP(S) or null')
        parsed = urlsplit(url)
        if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('service base_url must be HTTP(S) without credentials, query or fragment')
    if not isinstance(values.get('description', ''), str):
        raise ValueError('service description must be text')


@dataclass(frozen=True)
class ServiceDefinition:
    id: str
    protocols: frozenset[str]
    validate: Callable[[str, str, dict[str, Any]], None] = _accept_options
    prefix_bound: bool = False
    responses_store: bool = True
    parallel_control: bool = True
    chat_token_field: str = 'max_tokens'
    chat_stream_usage: bool = True
    base_url: str | None = None
    description: str = ''
    protocol_overrides: dict[str, dict[str, Any]] = field(default_factory=dict)
    label: str = ''
    default_protocol: str = ''
    api_key_env: str = ''
    input_count: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', self.id):
            raise ValueError('service needs a stable ID')
        if not self.protocols or any(not isinstance(p, str) or not p for p in self.protocols) or not callable(self.validate):
            raise ValueError('service needs protocols and a pure validator')
        object.__setattr__(self, 'protocols', frozenset(self.protocols))
        _validate_controls({name: getattr(self, name) for name in _CONTROLS})
        overrides = json_mapping(self.protocol_overrides, 'service protocol controls')
        if overrides.keys() - self.protocols:
            raise ValueError('unsupported service protocol override')
        for values in overrides.values():
            _validate_controls(json_mapping(values, 'service protocol controls'))
        object.__setattr__(self, 'protocol_overrides', overrides)
        if not isinstance(self.label, str) or not isinstance(self.default_protocol, str):
            raise ValueError('service setup metadata must be text')
        if self.default_protocol and self.default_protocol not in self.protocols:
            raise ValueError('service default_protocol must be supported')
        if not isinstance(self.api_key_env, str) or (self.api_key_env and not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', self.api_key_env)):
            raise ValueError('service api_key_env must name an environment variable')


def parse_service_table(text: str) -> tuple[ServiceDefinition, ...]:
    """Read one data-only table. Model names and parameter policies are not fields."""
    try:
        root = json_mapping(yaml.safe_load(text), 'service table')
    except yaml.YAMLError as exc:
        raise ValueError('invalid service table YAML') from exc
    if root.keys() != {'services'}:
        raise ValueError('service table requires only services')
    rows = json_mapping(root['services'], 'services')
    result = []
    for identity, raw in rows.items():
        row = json_mapping(raw, 'service entry')
        if row.keys() != {'label', 'default_protocol', 'api_key_env', 'protocols'}:
            raise ValueError('service entry requires label, default_protocol, api_key_env and protocols')
        protocols = json_mapping(row.pop('protocols'), 'service protocols')
        result.append(ServiceDefinition(identity, frozenset(protocols), protocol_overrides=protocols, **row))
    return tuple(result)


_BUILTINS = parse_service_table(files(__package__).joinpath('services.yaml').read_text(encoding='utf-8'))
_SERVICES = {item.id: item for item in _BUILTINS}


def builtin_services() -> tuple[ServiceDefinition, ...]:
    """Setup metadata from the same table used to resolve runtime endpoints."""
    return _BUILTINS


def register_service(definition: ServiceDefinition) -> None:
    if definition.id in _SERVICES:
        raise ValueError('service ID must be nonempty and distinct')
    _SERVICES[definition.id] = definition


def service_definition(service: str, protocol: str) -> ServiceDefinition:
    try:
        definition = _SERVICES[service]
    except KeyError as exc:
        raise ValueError('unknown model service: ' + service) from exc
    if protocol not in definition.protocols and service != 'generic':
        raise ValueError('model service does not support protocol: ' + protocol)
    overrides = definition.protocol_overrides.get(protocol)
    return replace(definition, **overrides) if overrides else definition


__all__ = ['ServiceDefinition', 'builtin_services', 'parse_service_table', 'register_service', 'service_definition']
