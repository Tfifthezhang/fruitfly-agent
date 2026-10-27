"""Stateless Chat Completions messages, with exact service-owned continuation."""
from __future__ import annotations

import json
from typing import Any, Callable

from fruitfly_agent.core.data_model import (AgentMessage, AssistantMessage, UserMessage,
    ToolResultMessage, CustomMessage, TextBlock, ImageBlock)
from fruitfly_agent.core.errors import FatalError


def convert_to_chat(messages: list[AgentMessage], *, replay: Callable | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for message in messages:
        if isinstance(message, UserMessage):
            content: Any = message.content
            if not isinstance(content, str):
                content = [{'type': 'text', 'text': b.text} if isinstance(b, TextBlock) else
                    {'type': 'image_url', 'image_url': {'url': f'data:{b.media_type};base64,{b.data}'}}
                    for b in content]
            out.append({'role': 'user', 'content': content})
        elif isinstance(message, AssistantMessage):
            original = replay(message, out) if replay else None
            if original is not None:
                out.extend(original)
                continue
            item: dict[str, Any] = {'role': 'assistant', 'content': message.text or None}
            if message.tool_calls:
                item['tool_calls'] = [{'id': call.id, 'type': 'function', 'function': {
                    'name': call.name, 'arguments': json.dumps(call.input)}} for call in message.tool_calls]
            out.append(item)
        elif isinstance(message, ToolResultMessage):
            if any(isinstance(b, ImageBlock) for b in message.content):
                raise FatalError('Chat Completions tool results support text only; use Responses or Messages for image results')
            out.append({'role': 'tool', 'tool_call_id': message.tool_call_id, 'content': message.text})
        elif isinstance(message, CustomMessage):
            out.append({'role': 'user', 'content': message.text})
    return out or [{'role': 'user', 'content': 'Continue.'}]


__all__ = ['convert_to_chat']
