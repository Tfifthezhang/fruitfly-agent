"""Frontend input contract; terminal adapters need no runtime-layer imports."""
from __future__ import annotations

from fruitfly_agent.core.data_model import ImageBlock as ImageAttachment, TextBlock
from fruitfly_agent.core.data_model.media import UserContent, normalize_input


def image_input(text: str, images: list[ImageAttachment]) -> UserContent:
    if not images:
        return normalize_input(text)
    blocks: list[TextBlock | ImageAttachment] = [TextBlock(text)] if text else []
    blocks.extend(images)
    return normalize_input(blocks)


__all__ = ['ImageAttachment', 'UserContent', 'normalize_input', 'image_input']
