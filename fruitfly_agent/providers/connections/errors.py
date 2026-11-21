"""Bounded subscription failure codes; never retain raw remote messages."""
from __future__ import annotations
from typing import Any
from fruitfly_agent.core.observation import FailureInfo
from fruitfly_agent.core.errors import FatalError, RetryableError, TaggedError

_CODES = {
    'subscription_sharing_usage_limit_exceeded': 'subscription_exhausted',
    'insufficient_quota': 'subscription_exhausted',
    'subscription_sharing_usage_unavailable': 'subscription_unavailable',
    'subscription_sharing_user_unavailable': 'subscription_unavailable',
    'subscription_sharing_unsupported_capability': 'unsupported_capability',
    'subscription_sharing_route_not_supported': 'unsupported_route',
    'subscription_sharing_invalid_user': 'authentication_required',
    'chatpass_v2_scope_not_authorized': 'authentication_required',
    'chatpass_v2_invalid_authorization_context': 'authentication_required',
}

def connection_error(value: Any) -> TaggedError | None:
    if hasattr(value, 'model_dump'):
        value = value.model_dump()
    if not isinstance(value, dict):
        return None
    error = value.get('error', value)
    if not isinstance(error, dict):
        return None
    kind = _CODES.get(str(error.get('code', '')))
    if kind is None:
        return None
    cls = RetryableError if kind == 'subscription_unavailable' else FatalError
    return cls('Model connection: ' + kind.replace('_', ' '), details={'kind': kind, 'diagnostics': {'failure_category': kind, 'evidence_kind': 'provider_code'},
        'failure': FailureInfo('provider', 'request', kind, 'provider_code').to_dict()})

def response_error(value: Any) -> TaggedError:
    return connection_error(value) or FatalError('Model response failed', details={'kind': 'response_failed'})
