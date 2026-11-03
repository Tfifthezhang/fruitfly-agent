"""Read text or images through the injected execution environment.

Text: offset/limit pagination with continuation hints ("Use offset=N").
Images: binary sniff → sent to the model as an image block.
"""

from __future__ import annotations

import base64
from typing import Callable

from fruitfly_agent.core.data_model import AgentToolResult, ImageBlock, TextBlock
from .presentation import file_call, text_result
from fruitfly_agent.core.tool_runtime import AgentTool, ToolCallContext
from fruitfly_agent.core.tool_runtime.authorization import ToolPermission
from .path_utils import resolve_read_path
from .truncate import DEFAULT_MAX_BYTES, DEFAULT_MAX_LINES, truncate_head
from fruitfly_agent.core.data_model.media import image_type, validate_image, decode_text_file

_READ_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "File path (relative or absolute) or registered read-only resource:// reference"},
        "character_offset": {"type": "integer", "description": "Zero-based character offset; use with character_limit instead of line offset/limit"},
        "character_limit": {"type": "integer", "description": "Maximum source characters (1–24000; default 12000)"},
        "offset": {
            "type": "integer",
            "description": "Line number to start reading from (1-indexed)",
        },
        "limit": {"type": "integer", "description": "Maximum number of lines to read"},
    },
    "required": ["path"],
}


def character_page(text, arguments):
    if 'character_offset' not in arguments and 'character_limit' not in arguments:
        return None
    if 'offset' in arguments or 'limit' in arguments:
        raise ValueError('choose line pagination or character pagination')
    start, limit = arguments.get('character_offset', 0), arguments.get('character_limit', 12000)
    if type(start) is not int or not 0 <= start <= len(text) or type(limit) is not int or not 1 <= limit <= 24000:
        raise ValueError('character pagination requires a source offset and a limit within 1..24000')
    page = truncate_head(text[start:start + limit]).content
    end = start + len(page)
    if end < len(text):
        page += f'\n[Characters {start}–{end} of {len(text)}. Use character_offset={end}, character_limit={limit} to continue.]'
    return page


async def _execute(ctx: ToolCallContext, register: Callable[[bytes, str, str], str] | None = None, resources=None) -> AgentToolResult:
    path = ctx.args["path"]
    offset = ctx.args.get("offset")
    limit = ctx.args.get("limit")

    from .resources import is_resource
    if is_resource(path):
        if resources is None:
            raise ValueError('resource owner is unavailable')
        bytes_data = resources.read(path.lstrip('@'))
    else:
        if ctx.env is None:
            raise RuntimeError('read requires an ExecutionEnv')
        resolved = resolve_read_path(ctx.env, path)
        data = ctx.env.read_binary_file(resolved)
        if not data.is_ok:
            raise RuntimeError(f'Could not read file: {path}. {data.error}')
        bytes_data = data.unwrap()
    mime = image_type(bytes_data)
    if mime is not None:
        mime = validate_image(bytes_data)
        resource = register(bytes_data, mime, 'tool:read') if register is not None else None
        return AgentToolResult(
            content=[
                TextBlock(text=f"Read image file [{mime}]"),
                ImageBlock(data=base64.b64encode(bytes_data).decode("ascii"), media_type=mime),
                *([TextBlock(text=f'Media resource: {resource}')] if resource else []),
            ]
        )

    text = decode_text_file(bytes_data)
    page = character_page(text, ctx.args)
    if page is not None:
        return AgentToolResult(content=[TextBlock(text=page)])
    all_lines = text.split("\n")
    total_lines = len(all_lines)
    start = max(0, (offset - 1) if offset else 0)
    if start >= total_lines and total_lines > 0:
        raise RuntimeError(f"Offset {offset} is beyond end of file ({total_lines} lines total)")
    selected = all_lines[start:] if limit is None else all_lines[start : start + limit]

    truncation = truncate_head("\n".join(selected))
    output = truncation.content
    if truncation.truncated:
        end_line = start + truncation.output_lines
        next_offset = end_line + 1
        partial_line = truncation.output_lines > 0 and (
            output.split("\n")[-1] != selected[truncation.output_lines - 1]
        )
        if partial_line:
            output += (
                f"\n\n[Line {end_line} exceeds the byte limit and was clipped."
                " Use character_offset/character_limit to inspect omitted characters.]"
            )
        continuation = f" Use offset={next_offset} to continue." if end_line < total_lines else ""
        output += f"\n\n[Showing lines {start + 1}-{end_line} of {total_lines}.{continuation}]"
    elif limit is not None and start + limit < total_lines:
        next_offset = start + limit + 1
        output += f"\n\n[{total_lines - (start + limit)} more lines in file. Use offset={next_offset} to continue.]"
    return AgentToolResult(content=[TextBlock(text=output)])


def create_read_tool(register_media: Callable[[bytes, str, str], str] | None = None, *, resources=None) -> AgentTool:
    async def execute(ctx: ToolCallContext) -> AgentToolResult:
        return await _execute(ctx, register_media, resources)

    return AgentTool(
        permission=ToolPermission("read", ("path",)),
        name="read",
        present_call=lambda args: file_call("read", args),
        present_result=lambda result: text_result("read", result),
        label="Read file",
        description=(
            "Read a file in the selected execution environment or a registered resource:// reference. "
            "Use for inspecting source code, configuration, logs and saved artifacts. "
            "Supports text files and images "
            f"(jpg, png, gif, webp; up to 10 MiB per image). Unsupported binary files are rejected. Text output is truncated to {DEFAULT_MAX_LINES} "
            f"lines or {DEFAULT_MAX_BYTES // 1024}KB (whichever is hit first). "
            "Use line offset/limit or character_offset/character_limit for large text."
        ),
        parameters=_READ_SCHEMA,
        execute=execute,
    )
