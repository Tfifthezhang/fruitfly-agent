"""Exact request preparation and count capabilities without endpoint guessing."""
from __future__ import annotations

from typing import Any


OPENAI_COUNT_FIELDS = frozenset({'model', 'input', 'instructions', 'tools', 'parallel_tool_calls',
    'personality', 'reasoning', 'text', 'tool_choice', 'truncation', 'extra_body', 'extra_headers', 'extra_query'})


def supports_count(provider: Any) -> bool:
    return provider.protocol == 'responses' and provider.service == 'openai'


def can_rebase(provider: Any, before: Any, after: Any) -> bool:
    if not getattr(getattr(provider, '_replay', None), 'prefix_bound', False):
        return True
    # Exact ordered state is bound to a signed prefix. Never invent a new user turn.
    from fruitfly_agent.core.data_model import AssistantMessage, UserMessage
    latest_user = max((i for i, m in enumerate(before) if isinstance(m, UserMessage)), default=-1)
    active = any(isinstance(m, AssistantMessage) and m.tool_calls and m.provider_state
                 for m in before[latest_user + 1:])
    return not active or [m.to_dict() for m in before] == [m.to_dict() for m in after]
