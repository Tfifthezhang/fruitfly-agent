"""FruitFlyAgent messages to stateless OpenAI Responses API input items."""

from __future__ import annotations

import json
from typing import Callable

from fruitfly_agent.core.data_model import (
    AgentMessage,
    AssistantMessage,
    CustomMessage,
    ImageBlock,
    TextBlock,
    ToolCallBlock,
    ToolResultMessage,
    UserMessage,
)


def convert_to_openai(messages: list[AgentMessage], *, replay: Callable | None = None) -> list[dict]:
    out: list[dict] = []
    for message in messages:
        if isinstance(message, UserMessage):
            if isinstance(message.content, str):
                out.append({"role": "user", "content": message.content})
            else:
                content = []
                for block in message.content:
                    if isinstance(block, TextBlock):
                        content.append({"type": "input_text", "text": block.text})
                    elif isinstance(block, ImageBlock):
                        content.append({
                            "type": "input_image",
                            "image_url": f"data:{block.media_type};base64,{block.data}",
                        })
                out.append({"role": "user", "content": content})
        elif isinstance(message, AssistantMessage):
            original = replay(message, out) if replay is not None else None
            if original is not None:
                out.extend(original)
                continue
            texts = [b.text for b in message.content if isinstance(b, TextBlock)]
            if texts:
                out.append({"role": "assistant", "content": "".join(texts)})
            for call in message.content:
                if isinstance(call, ToolCallBlock):
                    out.append({
                        "type": "function_call",
                        "call_id": call.id,
                        "name": call.name,
                        "arguments": json.dumps(call.input),
                    })
        elif isinstance(message, ToolResultMessage):
            output = [{'type': 'input_text', 'text': b.text} if isinstance(b, TextBlock) else
                      {'type': 'input_image', 'image_url': f'data:{b.media_type};base64,{b.data}'}
                      for b in message.content]
            out.append({
                "type": "function_call_output",
                "call_id": message.tool_call_id,
                "output": output if any(isinstance(b, ImageBlock) for b in message.content) else message.text,
            })
        elif isinstance(message, CustomMessage):
            out.append({"role": "user", "content": message.text})
    if not out:
        out.append({"role": "user", "content": "Continue."})
    return out


__all__ = ["convert_to_openai"]
