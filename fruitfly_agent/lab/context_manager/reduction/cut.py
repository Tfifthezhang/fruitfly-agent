"""Select whole turns without splitting tool calls and results."""

from __future__ import annotations

from typing import Callable

from fruitfly_agent.core.data_model import (
    AgentMessage,
    AssistantMessage, ToolResultMessage,
    CUSTOM_KIND_COMPACTION,
    CustomMessage,
    UserMessage,
)


def _is_valid_cut_point(message: AgentMessage) -> bool:
    if isinstance(message, UserMessage):
        return True
    if isinstance(message, CustomMessage) and message.kind == CUSTOM_KIND_COMPACTION:
        return True
    return False


from fruitfly_agent.core.context.validation import valid_tool_links


def find_cut_point(
    messages: list[AgentMessage],
    keep_recent_tokens: int,
    estimate: Callable[[AgentMessage], int],
    *, allow_intra_turn: bool = False,
) -> int | None:
    """Index to cut at: messages[cut:] are retained.

    Returns None when there is nothing safe to cut (empty history, no valid
    boundary, or the boundary is the very first message).
    """
    if not messages:
        return None

    if not valid_tool_links(messages):
        return None
    safe = set()
    pending: set[str] = set()
    for index, message in enumerate(messages):
        if not pending and _is_valid_cut_point(message):
            safe.add(index)
        if isinstance(message, AssistantMessage):
            pending.update(call.id for call in message.tool_calls)
        elif isinstance(message, ToolResultMessage):
            pending.remove(message.tool_call_id)

    if allow_intra_turn:
        # Preserve user boundaries when they fit; otherwise admit any completed batch.
        fitting = [i for i in safe if i > 0 and sum(estimate(m) for m in messages[i:]) <= keep_recent_tokens]
        if not fitting:
            pending = set()
            for index, message in enumerate(messages):
                if index > 0 and not pending and isinstance(message, AssistantMessage):
                    safe.add(index)
                if isinstance(message, AssistantMessage):
                    pending.update(call.id for call in message.tool_calls)
                elif isinstance(message, ToolResultMessage):
                    pending.remove(message.tool_call_id)

    accumulated = 0
    nearest_candidate: int | None = None
    for i in range(len(messages) - 1, -1, -1):
        accumulated += estimate(messages[i])
        # Keep the oldest complete boundary that still fits the target.
        # If the newest turn alone exceeds it, extend to that turn's start.
        if accumulated <= keep_recent_tokens and i in safe:
            nearest_candidate = i
        if accumulated >= keep_recent_tokens:
            if nearest_candidate is None:
                # No boundary in the kept region: extend the scan backwards
                # until the first boundary, keeping the whole turn (#1555 fix).
                for j in range(i, -1, -1):
                    if j in safe:
                        nearest_candidate = j
                        break
            if nearest_candidate is None:
                return None
            # Cut must leave something before it (never no-op).
            return nearest_candidate if nearest_candidate > 0 else None

    # The whole history is smaller than keep_recent_tokens: nothing to cut.
    return None


__all__ = ["find_cut_point", "valid_tool_links"]
