"""Read explicitly selected local images; remote paths remain tool-owned."""
from __future__ import annotations

from pathlib import Path
from dataclasses import replace
from inspect import isawaitable

from fruitfly_agent.core.data_model import ImageBlock, TextBlock, encode_image_bytes
from fruitfly_agent.core.data_model.media import MAX_IMAGE_BYTES, image_bytes, validate_image


def load_image(path: str, *, workspace: Path) -> ImageBlock:
    source = Path(path).expanduser()
    if not source.is_absolute():
        source = workspace / source
    if not source.is_file():
        raise ValueError('attachment must be a regular local image file')
    with source.open('rb') as stream:
        data = stream.read(MAX_IMAGE_BYTES + 1)
    mime = validate_image(data)
    return encode_image_bytes(data, mime)


def retain_tool_media(config, media):
    """Use the existing result rewrite port for every tool, including MCP."""
    previous = config.after_tool_call

    async def retain(ctx, result):
        if previous is not None:
            rewritten = previous(ctx, result)
            if isawaitable(rewritten):
                rewritten = await rewritten
            if rewritten is not None:
                result = rewritten
        references = []
        for block in result.content:
            if isinstance(block, ImageBlock):
                resource = media.put(image_bytes(block), block.media_type, 'tool:' + ctx.name)
                label = f'Media resource: {resource}'
                if not any(isinstance(b, TextBlock) and b.text == label for b in result.content):
                    references.append(TextBlock(label))
        return replace(result, content=[*result.content, *references])

    return replace(config, after_tool_call=retain)
