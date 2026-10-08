"""Write files through the injected execution environment."""

from __future__ import annotations

from fruitfly_agent.core.data_model import AgentToolResult, TextBlock
from fruitfly_agent.core.tool_runtime import AgentTool, ToolCallContext
from fruitfly_agent.core.tool_runtime.authorization import ToolPermission
from .file_queue import with_file_mutation_queue
from .path_utils import normalize_tool_path

_WRITE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "Path to the file to write (relative or absolute)"},
        "content": {"type": "string", "description": "Content to write to the file"},
    },
    "required": ["path", "content"],
}


async def _execute(ctx: ToolCallContext) -> AgentToolResult:
    if ctx.env is None:
        raise RuntimeError("write requires an ExecutionEnv")
    path = ctx.args["path"]
    content = ctx.args["content"]
    resolved = ctx.env.absolute_path(normalize_tool_path(path))
    if not resolved.is_ok:
        raise RuntimeError(f"Could not resolve path: {path}. {resolved.error}")
    absolute = resolved.unwrap()

    async def write() -> AgentToolResult:
        result = ctx.env.write_file(absolute, content)
        if not result.is_ok:
            raise RuntimeError(f"Could not write file: {path}. {result.error}")
        return AgentToolResult(
            content=[TextBlock(text=f"Successfully wrote {len(content)} characters to {path}")]
        )

    return await with_file_mutation_queue(ctx.env, absolute, write)


def create_write_tool() -> AgentTool:
    return AgentTool(
        permission=ToolPermission("write", ("path",)),
        name="write",
        label="write",
        description=(
            "Write content to a file. Creates the file if it doesn't exist, "
            "overwrites if it does. Automatically creates parent directories."
        ),
        parameters=_WRITE_SCHEMA,
        execute=_execute,
    )
