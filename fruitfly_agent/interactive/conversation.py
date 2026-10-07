"""Project canonical Core messages into immutable frontend history views."""

from collections.abc import Iterable

from fruitfly_agent.core.data_model import (
    AgentMessage, AssistantMessage, ImageBlock, TextBlock, ThinkingBlock,
    ToolCallBlock, ToolResultMessage, UserMessage,
)

from .models import ConversationBlock, ConversationMessage


def conversation_snapshot(messages: Iterable[AgentMessage]) -> tuple[ConversationMessage, ...]:
    result: list[ConversationMessage] = []
    tools: dict[str, str] = {}
    for message in messages:
        if not isinstance(message, (UserMessage, AssistantMessage, ToolResultMessage)):
            # Internal context summaries are not user/assistant conversation.
            continue
        blocks: list[ConversationBlock] = []
        content = message.content
        if isinstance(content, str):
            blocks.append(ConversationBlock("text", content))
        else:
            for block in content:
                if isinstance(block, TextBlock):
                    if blocks and blocks[-1].kind == "text":
                        blocks[-1] = ConversationBlock("text", blocks[-1].text + block.text)
                    else:
                        blocks.append(ConversationBlock("text", block.text))
                elif isinstance(block, ImageBlock):
                    blocks.append(ConversationBlock("image", block.media_type))
                elif isinstance(block, ThinkingBlock):
                    blocks.append(ConversationBlock("thinking"))
                elif isinstance(block, ToolCallBlock):
                    tools[block.id] = block.name
                    blocks.append(ConversationBlock("tool_call", block.name))
        if isinstance(message, ToolResultMessage):
            result.append(ConversationMessage(
                "tool", tuple(blocks), tools.get(message.tool_call_id, message.tool_call_id),
                message.is_error,
            ))
        else:
            result.append(ConversationMessage(
                "user" if isinstance(message, UserMessage) else "assistant", tuple(blocks),
            ))
    return tuple(result)
