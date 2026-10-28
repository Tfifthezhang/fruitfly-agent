"""Message pairing and replay constraints shared by all context methods."""
from ..data_model.messages import AssistantMessage, ToolResultMessage


def valid_tool_links(messages) -> bool:
    pending, seen = set(), set()
    for message in messages:
        if isinstance(message, AssistantMessage):
            for call in message.tool_calls:
                if not call.id or call.id in seen:
                    return False
                seen.add(call.id)
                pending.add(call.id)
        elif isinstance(message, ToolResultMessage):
            if message.tool_call_id not in pending:
                return False
            pending.remove(message.tool_call_id)
    return not pending


def can_rebase_context(provider, before, after) -> bool:
    check = getattr(provider, 'can_rebase_context', None)
    return bool(check(before, after)) if callable(check) else True
