"""Offline request/transport validation; runtime-owned fields cannot be overridden."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import fields
import json
import math
from typing import Any

from .transport import TransportPolicy, validate_retries

RESERVED = frozenset({'model', 'input', 'messages', 'instructions', 'system', 'tools',
    'stream', 'max_tokens', 'max_output_tokens', 'max_completion_tokens',
    'previous_response_id', 'conversation', 'background', 'api_key', 'base_url'})
TRANSPORT_FIELDS = frozenset({f.name for f in fields(TransportPolicy)} | {'retry_max', 'retry_base_delay'})
_OPTIONS = {
    'responses': {'reasoning', 'text', 'temperature', 'top_p', 'tool_choice', 'top_logprobs',
               'include', 'user', 'service_tier', 'prompt_cache_key', 'prompt_cache_retention'},
    'messages': {'thinking', 'output_config', 'temperature', 'top_p', 'top_k',
                  'tool_choice', 'stop_sequences', 'metadata', 'service_tier'},
    'chat-completions': {'reasoning_effort', 'temperature', 'top_p', 'tool_choice',
                    'response_format', 'stop', 'seed', 'presence_penalty', 'frequency_penalty',
                    'logprobs', 'top_logprobs', 'user', 'service_tier'},
}


def json_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or any(not isinstance(k, str) for k in value):
        raise ValueError(label + ' must be a string-keyed mapping')
    def check(item: Any) -> None:
        if isinstance(item, dict):
            if any(not isinstance(k, str) for k in item):
                raise ValueError(label + ' requires string keys')
            for v in item.values():
                check(v)
        elif isinstance(item, list):
            for v in item:
                check(v)
        elif item is not None and type(item) not in (str, int, float, bool):
            raise ValueError(label + ' requires JSON values')
    check(value)
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(label + ' requires finite JSON values') from exc
    return deepcopy(value)


def validate_transport(value: Any) -> dict[str, Any]:
    result = json_mapping(value, 'transport')
    unknown = result.keys() - TRANSPORT_FIELDS
    if unknown:
        raise ValueError('unknown transport fields: ' + ', '.join(sorted(unknown)))
    TransportPolicy(**{k: v for k, v in result.items() if k not in {'retry_max', 'retry_base_delay'}})
    validate_retries(result.get('retry_max', 3), result.get('retry_base_delay', 1.0))
    return result


def validate_request_options(protocol: str, value: Any) -> dict[str, Any]:
    result = json_mapping(value, 'parameters')
    if result.keys() & TRANSPORT_FIELDS:
        raise ValueError('waiting and retry options belong in transport')
    forbidden = result.keys() & (RESERVED | {'store', 'parallel_tool_calls'})
    if forbidden:
        raise ValueError('runtime-owned request fields: ' + ', '.join(sorted(forbidden)))
    if protocol in _OPTIONS:
        unknown = result.keys() - (_OPTIONS[protocol] | {'extra_body', 'extra_headers'})
        if unknown:
            raise ValueError('unknown ' + protocol + ' parameters: ' + ', '.join(sorted(unknown)))
    extra = result.get('extra_body', {})
    json_mapping(extra, 'parameters.extra_body')
    overlap = extra.keys() & (RESERVED | TRANSPORT_FIELDS | {'store', 'parallel_tool_calls', 'stream_options'} | result.keys())
    if overlap:
        raise ValueError('extra_body overrides protected or duplicate fields: ' + ', '.join(sorted(overlap)))
    headers = result.get('extra_headers', {})
    if not isinstance(headers, dict) or any(not isinstance(k, str) or not isinstance(v, str)
            or k.lower() in {'authorization', 'x-api-key', 'api-key', 'cookie'}
            or '\n' in k + v or '\r' in k + v for k, v in headers.items()):
        raise ValueError('extra_headers must contain non-secret feature headers')
    for field, lower, upper in (('temperature', 0, 2), ('top_p', 0, 1),
                                 ('presence_penalty', -2, 2), ('frequency_penalty', -2, 2)):
        if field in result:
            v = result[field]
            if type(v) not in (int, float) or not math.isfinite(v) or not lower <= v <= upper:
                raise ValueError(field + ' is outside its supported numeric range')
    for field in ('reasoning', 'thinking', 'output_config', 'text', 'response_format'):
        if field in result and not isinstance(result[field], dict):
            raise ValueError(field + ' must be a mapping')
    if 'reasoning' in result:
        reasoning = result['reasoning']
        if reasoning.keys() - {'effort', 'summary', 'context'}:
            raise ValueError('unknown reasoning fields')
        if 'effort' in reasoning and reasoning['effort'] not in {'none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max'}:
            raise ValueError('unsupported reasoning.effort')
    if 'thinking' in result and result['thinking'].get('type') not in {'enabled', 'disabled', 'adaptive'}:
        raise ValueError('thinking.type must be enabled, disabled or adaptive')
    if 'thinking' in result and result['thinking'].keys() - {'type', 'budget_tokens', 'display', 'block_binding'}:
        raise ValueError('unknown thinking fields')
    for field in ('text', 'response_format'):
        if field in result:
            fmt = result[field].get('format', {}) if field == 'text' else result[field]
            if not isinstance(fmt, dict) or fmt.get('type', 'text') not in {'text', 'json_object', 'json_schema'}:
                raise ValueError(field + ' requires a supported output format')
            if fmt.get('type') == 'json_schema':
                schema = fmt if field == 'text' else fmt.get('json_schema')
                if (not isinstance(schema, dict) or not isinstance(schema.get('name'), str)
                        or not schema['name'] or not isinstance(schema.get('schema'), dict)
                        or ('strict' in schema and type(schema['strict']) is not bool)):
                    raise ValueError(field + ' json_schema requires name, schema and optional boolean strict')
    return result


__all__ = ['validate_request_options', 'validate_transport']
