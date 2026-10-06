"""Convert AgentMessage values to Anthropic Messages input.

Pairing normalization: tool_results must reference a tool_use in a preceding
assistant message. Violations (harness bugs) are normalized away instead of
crashing the run: orphan tool_results are dropped, orphan tool_use blocks are
stripped from their assistant message. The first message is always user-role
(a bare "continue" user message is prepended when missing).
"""

from __future__ import annotations

from fruitfly_agent.core.data_model import (
    AgentMessage,
    AssistantMessage,
    CUSTOM_KIND_COMPACTION,
    CustomMessage,
    ImageBlock,
    TextBlock,
    ToolCallBlock,
    ToolResultMessage,
    UserMessage,
)

COMPACTION_SUMMARY_PREFIX = (
    "The conversation history before this point was compacted into the following summary:\n"
)


def _custom_to_text(message: CustomMessage) -> str:
    if message.kind == CUSTOM_KIND_COMPACTION:
        return COMPACTION_SUMMARY_PREFIX + message.text
    return message.text


def convert_to_anthropic(messages: list[AgentMessage]) -> list[dict]:
    """Convert AgentMessage[] to provider-ready dict messages.

    Pairing normalization: a tool_result is kept only when an assistant
    message has the matching tool_use; a tool_use block is kept only when a
    tool_result references it. Orphans are normalized away instead of
    crashing the request.
    """
    assistant_ids: set[str] = set()
    result_ids: set[str] = set()
    for m in messages:
        if isinstance(m, AssistantMessage):
            assistant_ids.update(tc.id for tc in m.tool_calls)
        elif isinstance(m, ToolResultMessage) and m.tool_call_id:
            result_ids.add(m.tool_call_id)

    out: list[dict] = []
    i = 0
    while i < len(messages):
        message = messages[i]

        if isinstance(message, ToolResultMessage):
            # Merge consecutive tool results into ONE user message (API contract).
            results: list[dict] = []
            while i < len(messages) and isinstance(messages[i], ToolResultMessage):
                result = messages[i]
                if result.tool_call_id in assistant_ids:
                    results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": result.tool_call_id,
                            "content": result.text,
                            "is_error": result.is_error,
                        }
                    )
                i += 1
            if results:
                out.append({"role": "user", "content": results})
            continue

        if isinstance(message, UserMessage):
            if isinstance(message.content, str):
                out.append({"role": "user", "content": message.content})
            else:
                content = [
                    (
                        {"type": "text", "text": b.text}
                        if isinstance(b, TextBlock)
                        else {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": b.media_type,
                                "data": b.data,
                            },
                        }
                    )
                    for b in message.content
                ]
                out.append({"role": "user", "content": content})
            i += 1
            continue

        if isinstance(message, AssistantMessage):
            content: list[dict] = []
            for block in message.content:
                if isinstance(block, TextBlock):
                    content.append({"type": "text", "text": block.text})
                elif isinstance(block, ToolCallBlock):
                    if block.id in result_ids:
                        content.append(
                            {
                                "type": "tool_use",
                                "id": block.id,
                                "name": block.name,
                                "input": block.input,
                            }
                        )
                # ThinkingBlock: dropped at the API boundary (not replayable).
            out.append({"role": "assistant", "content": content})
            i += 1
            continue

        if isinstance(message, CustomMessage):
            out.append({"role": "user", "content": _custom_to_text(message)})
            i += 1
            continue

        # Unknown role: skip defensively.
        i += 1

    if not out or out[0].get("role") != "user":
        out.insert(0, {"role": "user", "content": "Continue."})
    return out


__all__ = ["convert_to_anthropic", "COMPACTION_SUMMARY_PREFIX"]
