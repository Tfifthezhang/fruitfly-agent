"""Write files through the injected execution environment."""

from __future__ import annotations

from fruitfly_agent.runtime_spec.documents import parameter_default

from fruitfly_agent.core.data_model import AgentToolResult, TextBlock
from fruitfly_agent.lab.tools.presentation import file_call, text_result
from fruitfly_agent.core.tool_runtime import AgentTool, ToolCallContext
from fruitfly_agent.core.tool_runtime.authorization import ToolPermission
from fruitfly_agent.core.tool_runtime.schema import validate_tool_arguments
from fruitfly_agent.core.errors import Result
from fruitfly_agent.core.data_model.media import MAX_IMAGE_BYTES
from typing import Callable
from fruitfly_agent.lab.tools.file_queue import with_file_mutation_queue
from fruitfly_agent.lab.tools.path_utils import normalize_tool_path

_WRITE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "Path to the file to write (relative or absolute)"},
        "content": {"type": "string", "description": "Content to write to the file"},
        "resource_id": {"type": "string", "description": "Granted media resource ID; use instead of content to save original bytes"},
    },
    "required": ["path"],
    "additionalProperties": False,
}


def _validate(arguments):
    result = validate_tool_arguments(_WRITE_SCHEMA, arguments)
    if not result.is_ok:
        return result
    values = result.unwrap()
    if ('content' in values) == ('resource_id' in values):
        return Result.failure('write requires exactly one of content or resource_id')
    if not values.get('path') or ('resource_id' in values and not values['resource_id']):
        return Result.failure('write path and resource_id must be nonempty')
    return Result.success(values)


async def _execute(ctx: ToolCallContext, read_resource=None) -> AgentToolResult:
    checked = _validate(ctx.args)
    if not checked.is_ok:
        raise ValueError(checked.error)
    if ctx.env is None:
        raise RuntimeError("write requires an ExecutionEnv")
    path = ctx.args["path"]
    from fruitfly_agent.lab.tools.resources import is_resource
    if is_resource(path):
        raise ValueError("resources are read-only")
    if 'resource_id' in ctx.args:
        if read_resource is None:
            raise ValueError('write has no host media resource reader')
        content = read_resource(ctx.args['resource_id'])
        if not isinstance(content, bytes) or len(content) > MAX_IMAGE_BYTES:
            raise ValueError('media resource exceeds the 10 MiB save limit or is not bytes')
    else:
        content = checked.unwrap()['content']
    resolved = ctx.env.absolute_path(normalize_tool_path(path))
    if not resolved.is_ok:
        raise RuntimeError(f"Could not resolve path: {path}. {resolved.error}")
    absolute = resolved.unwrap()

    async def write() -> AgentToolResult:
        result = ctx.env.write_file(absolute, content)
        if not result.is_ok:
            raise RuntimeError(f"Could not write file: {path}. {result.error}")
        return AgentToolResult(
            content=[TextBlock(text=f"Successfully wrote {len(content)} {'bytes' if isinstance(content, bytes) else 'characters'} to {path}")]
        )

    return await with_file_mutation_queue(ctx.env, absolute, write)


def create_write_tool(read_resource: Callable[[str], bytes] | None = None) -> AgentTool:
    async def execute(ctx):
        return await _execute(ctx, read_resource)
    return AgentTool(
        permission=ToolPermission("write", ("path",)),
        name="write",
        present_call=lambda args: file_call("write", args),
        present_result=lambda result: text_result("write", result),
        label="Write file",
        description=(
            parameter_default(__package__, 'defaults.yaml', 'instructions.description')
        ),
        parameters=_WRITE_SCHEMA,
        execute=execute,
        validate_arguments=_validate,
    )
