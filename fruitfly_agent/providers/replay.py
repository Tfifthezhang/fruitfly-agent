"""Exact protocol continuation bound to response content, credentials and context."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import hmac
import json
from typing import Any, Callable

from fruitfly_agent.core.data_model import AssistantMessage, ProviderView, UserMessage
from fruitfly_agent.core.errors import FatalError
from .services import service_definition


def wire_value(value: Any) -> Any:
    """Copy SDK wire values without importing SDKs into message contracts."""
    if hasattr(value, 'model_dump'):
        return value.model_dump(mode='json', exclude_none=True)
    if isinstance(value, dict):
        return {k: wire_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [wire_value(v) for v in value]
    if hasattr(value, '__dict__'):
        return {k: wire_value(v) for k, v in vars(value).items() if not k.startswith('_')}
    return value


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


class ReplayBinding:
    def __init__(self, protocol: str, service: str, endpoint: str | None, api_key: str, *, namespace: str) -> None:
        # Persisted v1 continuation namespaces are independent of YAML field names.
        self.namespace, self.service = namespace, service
        self.prefix_bound = service_definition(service, protocol).prefix_bound
        identity = json.dumps([namespace, service, endpoint], separators=(',', ':')).encode()
        # A nonreversible keyed identity detects credential changes without storing keys.
        self.identity = hmac.new(api_key.encode(), identity, hashlib.sha256).hexdigest()

    def context(self, view: ProviderView, tools: list[dict[str, Any]]) -> dict[str, Any]:
        return {'identity': self.identity, 'model': view.model, 'system': view.system_prompt, 'tools': tools}

    def reader(self, view: ProviderView, tools: list[dict[str, Any]]) -> Callable:
        context = self.context(view, tools)
        last_user = max((i for i, m in enumerate(view.messages) if isinstance(m, UserMessage)), default=-1)
        active_ids = {id(m) for m in view.messages[last_user + 1:] if isinstance(m, AssistantMessage) and m.tool_calls}
        def read(message: AssistantMessage, prefix: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
            state = message.provider_state
            if state is None:
                return None
            if state.get('schema_version') != 1 or state.get('protocol') != self.namespace:
                valid = False
            else:
                valid = (state.get('identity') == self.identity
                    and state.get('model') == view.model
                    and state.get('content_hash') == digest([b.to_dict() for b in message.content]))
                if self.prefix_bound:
                    valid = valid and state.get('prefix_hash') == digest([context, prefix])
            if not valid:
                if id(message) in active_ids:
                    raise FatalError('Provider continuation no longer matches the model, credentials or request context; finish or restart this tool turn before changing configuration')
                return None
            payload = state.get('items')
            if not isinstance(payload, list) or any(not isinstance(item, dict) for item in payload):
                raise FatalError('Invalid persisted Provider continuation')
            if state.get('payload_hash') != digest(payload):
                raise FatalError('Provider continuation content differs from its recorded digest')
            return wire_value(payload)
        return read

    def attach(self, message: AssistantMessage, view: ProviderView, tools: list[dict[str, Any]],
               prefix: list[dict[str, Any]], items: list[dict[str, Any]]) -> AssistantMessage:
        state = {'schema_version': 1, 'protocol': self.namespace, 'identity': self.identity,
            'model': view.model, 'content_hash': digest([b.to_dict() for b in message.content]),
            'prefix_hash': digest([self.context(view, tools), prefix]),
            'items': wire_value(items), 'payload_hash': digest(items)}
        return replace(message, provider_state=state)


__all__ = ['ReplayBinding']
