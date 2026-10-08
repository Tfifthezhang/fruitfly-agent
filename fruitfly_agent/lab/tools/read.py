"""Read text or images through the injected execution environment.

Text: offset/limit pagination with continuation hints ("Use offset=N").
Images: binary sniff → sent to the model as an image block.
"""

from __future__ import annotations

import base64

from fruitfly_agent.core.data_model import AgentToolResult, ImageBlock, TextBlock
from fruitfly_agent.core.tool_runtime import AgentTool, ToolCallContext
from fruitfly_agent.core.tool_runtime.authorization import ToolPermission
from .path_utils import resolve_read_path
from .truncate import DEFAULT_MAX_BYTES, DEFAULT_MAX_LINES, truncate_head

_IMAGE_MAGIC: dict[bytes, str] = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"GIF87a": "image/gif",
    b"GIF89a": "image/gif",
    b"BM": "image/bmp",
}


def _sniff_image(data: bytes) -> str | None:
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    for magic, mime in _IMAGE_MAGIC.items():
        if data.startswith(magic):
            return mime
    return None


_READ_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "Path to the file to read (relative or absolute)"},
        "offset": {
            "type": "integer",
            "description": "Line number to start reading from (1-indexed)",
        },
        "limit": {"type": "integer", "description": "Maximum number of lines to read"},
    },
    "required": ["path"],
}


async def _execute(ctx: ToolCallContext) -> AgentToolResult:
    if ctx.env is None:
        raise RuntimeError("read requires an ExecutionEnv")
    path = ctx.args["path"]
    offset = ctx.args.get("offset")
    limit = ctx.args.get("limit")

    resolved = resolve_read_path(ctx.env, path)
    data = ctx.env.read_binary_file(resolved)
    if not data.is_ok:
        raise RuntimeError(f"Could not read file: {path}. {data.error}")

    bytes_data = data.unwrap()
    mime = _sniff_image(bytes_data)
    if mime is not None:
        return AgentToolResult(
            content=[
                TextBlock(text=f"Read image file [{mime}]"),
                ImageBlock(data=base64.b64encode(bytes_data).decode("ascii"), media_type=mime),
            ]
        )

    text = bytes_data.decode("utf-8", errors="replace")
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
                " Line offsets cannot retrieve its omitted characters; use bash to inspect the line.]"
            )
        continuation = f" Use offset={next_offset} to continue." if end_line < total_lines else ""
        output += f"\n\n[Showing lines {start + 1}-{end_line} of {total_lines}.{continuation}]"
    elif limit is not None and start + limit < total_lines:
        next_offset = start + limit + 1
        output += f"\n\n[{total_lines - (start + limit)} more lines in file. Use offset={next_offset} to continue.]"
    return AgentToolResult(content=[TextBlock(text=output)])


def create_read_tool() -> AgentTool:
    return AgentTool(
        permission=ToolPermission("read", ("path",)),
        name="read",
        label="read",
        description=(
            "Read the contents of a file. Supports text files and images "
            f"(jpg, png, gif, webp, bmp). Text output is truncated to {DEFAULT_MAX_LINES} "
            f"lines or {DEFAULT_MAX_BYTES // 1024}KB (whichever is hit first). "
            "Use offset/limit for large files."
        ),
        parameters=_READ_SCHEMA,
        execute=_execute,
    )
