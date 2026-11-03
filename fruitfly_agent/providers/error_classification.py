"""Provider-neutral classification for model API failures.

Vendor SDKs expose different exception classes and compatible endpoints often
change the error wording.  Adapters keep extracting transport metadata, while
this module maps the resulting exception into Core's stable error vocabulary.
"""

from __future__ import annotations

import json
import re
import socket
import ssl
import errno
from fruitfly_agent.core.observation import FailureCause, FailureInfo
from typing import Any

from fruitfly_agent.core.errors import FatalError, OverflowError, RetryableError, TaggedError


_OVERFLOW_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"prompt(?:[_ ]is)?[_ ]too[_ ]long",
        r"request_too_large",
        r"input is too long",
        r"exceeds (?:the )?context window",
        r"exceeds (?:the )?(?:model'?s )?maximum context length",
        r"maximum context length",
        r"input length .*exceeds (?:the )?(?:model'?s )?maximum context length",
        r"input token count.*exceeds the maximum",
        r"input tokens?.*(?:exceeds?|exceeded).*limit",
        r"maximum prompt length is [\d,]+",
        r"reduce the length of the messages",
        r"maximum context length is [\d,]+ tokens?",
        r"exceeds (?:the )?maximum allowed input length",
        r"input \([\d,]+ tokens?\) is longer than the model'?s context length",
        r"prompt token count of [\d,]+ exceeds the limit of [\d,]+",
        r"exceeds the available context size",
        r"greater than the context length",
        r"context window exceeds limit",
        r"exceeded model token limit",
        r"too large for model with [\d,]+ maximum context length",
        r"prompt has [\d,]+ tokens?, but the configured context size is [\d,]+ tokens?",
        r"model_context_window_exceeded",
        r"prompt too long; exceeded (?:max )?context length",
        r"range of input length should be",
        r"context[_ ]length[_ ]exceeded",
        r"too many tokens",
        r"token limit exceeded",
        r"\b4(?:00|13)\b.*\(no body\)",
    )
)

# These take precedence over broad fallbacks such as "too many tokens".
_NON_OVERFLOW_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"^(?:throttling error|service unavailable):",
        r"throttl",
        r"rate limit",
        r"too many requests",
        r"tokens? per (?:second|minute|hour|day)",
    )
)

_RETRYABLE_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"connection",
        r"timeout",
        r"network",
        r"rate limit",
        r"too many requests",
        r"throttl",
        r"overloaded",
        r"service unavailable",
    )
)

_RETRYABLE_STATUS_CODES = frozenset({408, 409, 429, 500, 502, 503, 504, 529})


def classify_provider_error(
    exc: Exception,
    *,
    status_code: int | None = None,
) -> TaggedError:
    """Map a vendor exception to Core's overflow/retryable/fatal taxonomy.

    Explicit overflow wording wins unless the same error clearly describes
    throttling.  An otherwise unknown HTTP 400 is marked for Core's guarded
    token-estimate fallback instead of being assumed to be overflow.
    """

    resolved_status = _status_code(exc, status_code)
    text = _classification_text(exc)
    non_overflow = any(pattern.search(text) for pattern in _NON_OVERFLOW_PATTERNS)
    causes = _exception_causes(exc)
    code = next((row['category'] for row in reversed(causes) if row['category'] != 'unknown'), 'unknown')
    evidence = 'exception_type' if code != 'unknown' else 'unknown'
    if code == 'unknown' and re.search(r'Unterminated string|Invalid JSON|Expecting (?:value|property name)', text, re.I):
        code, evidence = 'response_parse', 'message_pattern'
    if code == 'unknown' and resolved_status is not None:
        code = ('authentication' if resolved_status in {401, 403} else 'rate_limit' if resolved_status == 429
            else 'service_unavailable' if resolved_status >= 500 else 'http_error')
        evidence = 'http_status'
    details: dict[str, Any] = {'status_code': resolved_status,
        'diagnostics': {'causes': causes, 'failure_category': code, 'evidence_kind': evidence},
        'failure': FailureInfo('provider', 'request', code, evidence, exception_type=type(exc).__name__,
            causes=tuple(FailureCause(row['type'], row['category'], row.get('errno')) for row in causes),
            http_status=resolved_status).to_dict()}

    if not non_overflow and any(pattern.search(text) for pattern in _OVERFLOW_PATTERNS):
        return OverflowError(str(exc), details=details)
    if not non_overflow and resolved_status == 413:
        return OverflowError(str(exc), details=details)
    if resolved_status in _RETRYABLE_STATUS_CODES or any(
        pattern.search(text) for pattern in _RETRYABLE_PATTERNS
    ):
        return RetryableError(str(exc), details=details)
    if resolved_status == 400:
        details["unknown_400"] = True
    if isinstance(exc, FatalError):
        merged = dict(exc.details) if isinstance(exc.details, dict) else {}
        merged.update(details)
        return FatalError(str(exc), details=merged)
    return FatalError(str(exc), details=details)


def _exception_causes(exc: BaseException) -> list[dict[str, Any]]:
    """Retain structural causes, never exception bodies, request URLs or headers."""
    result: list[dict[str, Any]] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen and len(result) < 6:
        seen.add(id(current))
        category = 'unknown'
        if isinstance(current, socket.gaierror):
            category = 'dns'
        elif isinstance(current, ssl.SSLCertVerificationError):
            category = 'tls_certificate'
        elif isinstance(current, ssl.SSLError):
            category = 'tls'
        elif isinstance(current, TimeoutError):
            category = 'timeout'
        elif isinstance(current, ConnectionRefusedError):
            category = 'connection_refused'
        elif isinstance(current, ConnectionResetError):
            category = 'connection_reset'
        elif isinstance(current, ConnectionError):
            category = 'connection'
        if category == 'unknown':
            category = {'ConnectTimeout': 'connect_timeout', 'ReadTimeout': 'read_timeout',
                'WriteTimeout': 'write_timeout', 'PoolTimeout': 'pool_timeout',
                'ConnectError': 'connection', 'ReadError': 'connection_read', 'WriteError': 'connection_write',
                'ProxyError': 'proxy', 'RemoteProtocolError': 'response_protocol',
                'LocalProtocolError': 'request_protocol', 'JSONDecodeError': 'response_parse',
                'APIResponseValidationError': 'response_schema', 'APITimeoutError': 'timeout',
                'APIConnectionError': 'connection'}.get(type(current).__name__, 'unknown')
        if isinstance(current, json.JSONDecodeError):
            category = 'response_parse'
        row: dict[str, Any] = {'type': type(current).__name__[:80], 'category': category}
        number = getattr(current, 'errno', None)
        if type(number) is int:
            row['errno'] = number
            row['category'] = {errno.ECONNREFUSED: 'connection_refused', errno.ECONNRESET: 'connection_reset',
                errno.ENETUNREACH: 'network_unreachable', errno.EHOSTUNREACH: 'host_unreachable',
                errno.ETIMEDOUT: 'connect_timeout'}.get(number, category)
        result.append(row)
        current = current.__cause__ or (None if current.__suppress_context__ else current.__context__)
    return result


def _status_code(exc: Exception, explicit: int | None) -> int | None:
    if explicit is not None:
        return explicit
    direct = getattr(exc, "status_code", None)
    if isinstance(direct, int) and not isinstance(direct, bool):
        return direct
    if isinstance(exc, TaggedError) and isinstance(exc.details, dict):
        nested = exc.details.get("status_code")
        if isinstance(nested, int) and not isinstance(nested, bool):
            return nested
    return None


def _classification_text(exc: Exception) -> str:
    """Include common structured SDK fields without depending on an SDK type."""

    parts = [str(exc)]
    for attribute in ("code", "type", "body"):
        value = getattr(exc, attribute, None)
        if value is None:
            continue
        if isinstance(value, (dict, list, tuple)):
            try:
                parts.append(json.dumps(value, sort_keys=True, default=str))
            except (TypeError, ValueError):
                parts.append(str(value))
        else:
            parts.append(str(value))
    return "\n".join(parts)


__all__ = ["classify_provider_error"]
