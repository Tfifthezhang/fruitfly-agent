"""The builtin tool set: read, write, edit, bash."""

from __future__ import annotations

from fruitfly_agent.core.tool_runtime import AgentTool
from .bash import create_bash_tool
from .edit import create_edit_tool
from .read import create_read_tool
from .write import create_write_tool


def builtin_tools() -> list[AgentTool]:
    return [
        create_read_tool(),
        create_bash_tool(),
        create_edit_tool(),
        create_write_tool(),
    ]
