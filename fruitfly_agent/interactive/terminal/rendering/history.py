"""Static history presentation, independent of live events and execution."""

from fruitfly_agent.interactive.contracts.models import ConversationMessage
from fruitfly_agent.interactive.terminal.rendering.markdown import TerminalMarkdownRenderer
from fruitfly_agent.interactive.terminal.io.text import safe_terminal_text

_TOOL_RESULT_LIMIT = 800


def render_history_message(
    message: ConversationMessage, *, columns: int, terminal_ui: bool, color: bool,
) -> str:
    label = {"user": "You", "assistant": "FruitFlyAgent", "tool": "Tool"}[message.role]
    if message.role == "user" and color:
        label = f"\x1b[1m{label}\x1b[0m"
    if message.role == "tool":
        label += f" · {safe_terminal_text(message.tool_name)}"
        if message.is_error:
            label += " (error)"
    parts: list[str] = [label + "\n"]
    markdown = TerminalMarkdownRenderer(columns=columns, color=color) if terminal_ui else None
    remaining = _TOOL_RESULT_LIMIT
    for block in message.content:
        text = safe_terminal_text(block.text)
        if block.kind == "text":
            if message.role == "tool":
                visible = text[:remaining]
                remaining -= len(visible)
                if visible:
                    parts.append(visible.rstrip("\n") + "\n")
                if len(text) > len(visible):
                    parts.append("… [historical tool output truncated]\n")
            elif markdown is not None and message.role == "assistant":
                parts.append(markdown.render(text))
            else:
                parts.append(text.rstrip("\n") + "\n")
        elif block.kind == "image":
            parts.append(f"[Image attachment · {text}]\n")
        elif block.kind == "thinking":
            parts.append("[Reasoning omitted]\n")
        elif block.kind == "tool_call":
            parts.append(f"[Tool call · {text}]\n")
    return "".join(parts) + "\n"
