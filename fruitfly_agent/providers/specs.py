"""Immutable descriptions of model endpoints used in reproducible runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import re
from urllib.parse import urlsplit

from .request_options import json_mapping, validate_request_options, validate_transport
from .services import service_definition


@dataclass(frozen=True)
class ModelCapabilities:
    tools: bool = True
    parallel_tool_calls: bool = False
    vision: bool = False
    reasoning: bool = False
    streaming: bool = True

    def __post_init__(self) -> None:
        if any(type(value) is not bool for value in vars(self).values()):
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

    def __post_init__(self) -> None:
        if not all(isinstance(v, str) and v.strip() for v in (self.id, self.model, self.service)):
            raise ValueError('model identity and protocol must be nonempty strings')
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', self.provider.api_key_env):
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
        thinking = options.get('thinking', {})
        if 'budget_tokens' in thinking and (type(thinking['budget_tokens']) is not int
                or not 0 < thinking['budget_tokens'] < self.max_output_tokens):
            raise ValueError('thinking.budget_tokens must fit inside max_output_tokens')
        object.__setattr__(self, 'parameters', options)
        object.__setattr__(self, 'transport', validate_transport(self.transport))

    def to_dict(self) -> dict[str, Any]:
        return {'sdk': self.provider.sdk, 'protocol': self.provider.protocol, 'service': self.service, 'model': self.model,
            'api_key_env': self.provider.api_key_env, 'base_url': self.provider.base_url,
            'context_window': self.context_window, 'max_output_tokens': self.max_output_tokens,
            'capabilities': vars(self.capabilities).copy(), 'parameters': dict(self.parameters),
            'transport': dict(self.transport)}

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
            'context_window', 'max_output_tokens', 'capabilities', 'parameters', 'transport'}
        if unknown:
            raise ValueError('unknown model fields: ' + ', '.join(sorted(unknown)))
        missing = {'sdk', 'protocol', 'model', 'context_window'} - raw.keys()
        if missing:
            raise ValueError('missing model fields: ' + ', '.join(sorted(missing)))
        caps = raw.get("capabilities", {})
        if not isinstance(caps, dict):
            raise ValueError('capabilities must be a mapping')
        return cls(
            id=model_id,
            provider=ProviderSpec(
                sdk=raw["sdk"],
                protocol=raw["protocol"],
                api_key_env=raw.get("api_key_env") or _default_key_env(raw["sdk"]),
                base_url=raw.get("base_url"),
            ),
            model=raw["model"],
            context_window=raw["context_window"],
            max_output_tokens=raw.get("max_output_tokens", 4096),
            capabilities=ModelCapabilities(**caps),
            parameters=raw.get("parameters", {}),
            service=raw.get('service', 'generic'),
            transport=raw.get('transport', {}),
        )


def _default_key_env(sdk: str) -> str:
    return sdk.upper().replace('-', '_').replace('.', '_') + '_API_KEY'


__all__ = ["ModelCapabilities", "ProviderSpec", "ModelSpec"]
