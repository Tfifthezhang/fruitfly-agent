"""Immutable descriptions of model endpoints used in reproducible runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import re
from urllib.parse import urlsplit

from .request_options import json_mapping, validate_request_options, validate_transport
from .services import service_definition

MODEL_FIELD_ORDER = ('service', 'protocol', 'sdk', 'model', 'base_url', 'context_window',
    'max_output_tokens', 'api_key_env', 'capabilities', 'parameters', 'transport')


def ordered_model_entry(value: dict[str, Any]) -> dict[str, Any]:
    """Serialize model fields in setup order, with transport last."""
    extra_fields = ('connection', 'access', 'output_reserve')
    unknown = value.keys() - set(MODEL_FIELD_ORDER) - set(extra_fields)
    if unknown:
        raise ValueError('unknown model fields: ' + ', '.join(sorted(unknown)))
    return {name: value[name] for name in (*MODEL_FIELD_ORDER, *extra_fields) if name in value}


@dataclass(frozen=True)
class ModelCapabilities:
    tools: bool = True
    parallel_tool_calls: bool | None = False
    vision: bool = False
    reasoning: bool = False
    streaming: bool = True

    def __post_init__(self) -> None:
        if any(type(value) is not bool and not (name == 'parallel_tool_calls' and value is None)
               for name, value in vars(self).items()):
            raise ValueError('capabilities must be booleans')


@dataclass(frozen=True)
class ProviderSpec:
    sdk: str
    protocol: str
    api_key_env: str
    base_url: str | None = None

    def __post_init__(self) -> None:
        for name in ('sdk', 'protocol'):
            value = getattr(self, name)
            if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', value):
                raise ValueError(name + ' must be a nonempty identifier')


@dataclass(frozen=True)
class ModelSpec:
    id: str
    provider: ProviderSpec
    model: str
    context_window: int
    max_output_tokens: int = 4096
    capabilities: ModelCapabilities = field(default_factory=ModelCapabilities)
    parameters: dict[str, Any] = field(default_factory=dict)
    service: str = 'generic'
    transport: dict[str, Any] = field(default_factory=dict)
    access: dict[str, Any] | None = None
    output_reserve: int | None = None

    def __post_init__(self) -> None:
        if not all(isinstance(v, str) and v.strip() for v in (self.id, self.model, self.service)):
            raise ValueError('model identity and protocol must be nonempty strings')
        if self.access is not None:
            from .connections.contracts import ConnectionProfile
            from .connections.registry import builtin_connections
            connection = ConnectionProfile.from_dict(self.access)
            builtin_connections().resolve(connection, {'sdk': self.provider.sdk, 'protocol': self.provider.protocol,
                'service': self.service, 'base_url': self.provider.base_url})
            if self.provider.api_key_env:
                raise ValueError('Connected models cannot contain API key variables')
        if self.access and self.output_reserve is None:
            object.__setattr__(self, 'output_reserve', self.max_output_tokens)
        if self.access and not builtin_connections().get(self.access['integration']).output_enforced and self.max_output_tokens > (self.output_reserve or 0):
            raise ValueError('Requested output exceeds the confirmed model maximum')
        if self.output_reserve is not None and (type(self.output_reserve) is not int or not 0 < self.output_reserve < self.context_window):
            raise ValueError('output_reserve must fit inside context_window')
        if self.access is None and not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', self.provider.api_key_env):
            raise ValueError('credential references must name environment variables')
        for name in ('context_window', 'max_output_tokens'):
            if type(getattr(self, name)) is not int or getattr(self, name) <= 0:
                raise ValueError(name + ' must be a positive integer')
        if self.provider.base_url is not None:
            url = urlsplit(self.provider.base_url)
            if url.scheme not in {'http', 'https'} or not url.hostname or url.username or url.password or url.query or url.fragment:
                raise ValueError('base_url must be HTTP(S) without credentials, query or fragment')
        options = validate_request_options(self.provider.protocol, self.parameters)
        definition = service_definition(self.service, self.provider.protocol)
        definition.validate(self.provider.protocol, self.model, options)
        if self.access:
            policy = builtin_connections().get(self.access['integration']).request_policy
            validator = getattr(policy, 'validate', None)
            if validator is not None:
                validator(options)
        thinking = options.get('thinking', {})
        if 'budget_tokens' in thinking and (type(thinking['budget_tokens']) is not int
                or not 0 < thinking['budget_tokens'] < self.max_output_tokens):
            raise ValueError('thinking.budget_tokens must fit inside max_output_tokens')
        object.__setattr__(self, 'parameters', options)
        object.__setattr__(self, 'transport', validate_transport(self.transport))

    def to_dict(self) -> dict[str, Any]:
        return ordered_model_entry({'sdk': self.provider.sdk, 'protocol': self.provider.protocol, 'service': self.service, 'model': self.model,
            'api_key_env': self.provider.api_key_env, 'base_url': self.provider.base_url,
            'context_window': self.context_window, 'max_output_tokens': self.max_output_tokens,
            'capabilities': {name: value for name, value in vars(self.capabilities).items() if value is not None}, 'parameters': dict(self.parameters),
            'transport': dict(self.transport),
            **({'access': dict(self.access), 'output_reserve': self.output_reserve} if self.access else {})})

    def require(
        self, *, tools: bool = False, vision: bool = False, streaming: bool = True
    ) -> None:
        required = {"tools": tools, "vision": vision, "streaming": streaming}
        missing = [name for name, needed in required.items() if needed and not getattr(self.capabilities, name)]
        if missing:
            raise ValueError(f"model {self.id!r} lacks required capabilities: {', '.join(missing)}")

    @classmethod
    def from_dict(cls, model_id: str, raw: dict[str, Any]) -> "ModelSpec":
        raw = json_mapping(raw, 'model specification')
        unknown = raw.keys() - {'sdk', 'protocol', 'service', 'model', 'api_key_env', 'base_url',
            'context_window', 'max_output_tokens', 'capabilities', 'parameters', 'transport', 'access', 'output_reserve'}
        if unknown:
            raise ValueError('unknown model fields: ' + ', '.join(sorted(unknown)))
        missing = {'sdk', 'protocol', 'model', 'context_window'} - raw.keys()
        if missing:
            raise ValueError('missing model fields: ' + ', '.join(sorted(missing)))
        if raw.get('access') is not None and raw.get('api_key_env'):
            raise ValueError('Connected models cannot contain API key variables')
        if raw.get('access') is None and raw.get('output_reserve') is not None:
            raise ValueError('output_reserve requires an account connection')
        caps = raw.get("capabilities", {})
        if not isinstance(caps, dict):
            raise ValueError('capabilities must be a mapping')
        return cls(
            id=model_id,
            provider=ProviderSpec(
                sdk=raw["sdk"],
                protocol=raw["protocol"],
                api_key_env=(raw.get("api_key_env") or _default_key_env(raw["sdk"])) if not raw.get("access") else "",
                base_url=raw.get("base_url"),
            ),
            model=raw["model"],
            context_window=raw["context_window"],
            max_output_tokens=raw.get("max_output_tokens", 4096),
            capabilities=ModelCapabilities(**({'parallel_tool_calls': None, **caps} if raw.get('access') else caps)),
            parameters=raw.get("parameters", {}),
            service=raw.get('service', 'generic'),
            transport=raw.get('transport', {}),
            access=raw.get('access'),
            output_reserve=raw.get('output_reserve', raw.get('max_output_tokens') if raw.get('access') else None),
        )


def _default_key_env(sdk: str) -> str:
    return sdk.upper().replace('-', '_').replace('.', '_') + '_API_KEY'


__all__ = ["ModelCapabilities", "ProviderSpec", "ModelSpec", "MODEL_FIELD_ORDER", "ordered_model_entry"]
