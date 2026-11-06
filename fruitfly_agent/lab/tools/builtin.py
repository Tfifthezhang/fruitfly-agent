"""The builtin tool set: read, write, edit, bash."""

from __future__ import annotations

from fruitfly_agent.core.tool_runtime import AgentTool
from fruitfly_agent.lab.tools.methods.bash.algorithm import create_bash_tool
from fruitfly_agent.lab.tools.methods.edit.algorithm import create_edit_tool
from fruitfly_agent.lab.tools.methods.read.algorithm import create_read_tool
from fruitfly_agent.lab.tools.methods.write.algorithm import create_write_tool


def builtin_tools() -> list[AgentTool]:
    return [
        create_read_tool(),
        create_bash_tool(),
        create_edit_tool(),
        create_write_tool(),
    ]
