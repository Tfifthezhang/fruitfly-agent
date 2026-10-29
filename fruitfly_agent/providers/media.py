"""Capability-aware projections; original Session facts are never changed."""
from __future__ import annotations

from dataclasses import replace

from fruitfly_agent.core.data_model import AgentMessage, UserMessage, ToolResultMessage, ImageBlock, TextBlock
from fruitfly_agent.core.data_model.media import (UserContent, normalize_input, image_bytes,
    validate_image, MAX_IMAGES, MAX_MEDIA_BYTES)


class MediaInput:
    vision: bool | None = None

    def validate_input(self, content: UserContent) -> UserContent:
        return normalize_input(content, vision=self.vision)


def project_images(messages: list[AgentMessage], vision: bool | None) -> list[AgentMessage]:
    """Unknown direct adapters retain image support; catalog adapters declare it.

An incapable model gets an explicit observation instead of unreadable media.
Fresh user inputs are rejected separately before persistence. Historical media
remain available when a vision-capable model is selected again.
"""
    if vision is None:
        return messages
    result: list[AgentMessage] = []
    for message in messages:
        if isinstance(message, (UserMessage, ToolResultMessage)) and isinstance(message.content, list):
            content: list[TextBlock | ImageBlock] = []
            count, size = 0, 0
            for block in message.content:
                if not isinstance(block, ImageBlock):
                    content.append(block)
                    continue
                reason = ''
                if not vision:
                    reason = 'this model cannot view images'
                else:
                    try:
                        data = image_bytes(block)
                        if validate_image(data) != block.media_type:
                            raise ValueError('declared image type differs from its contents')
                        if count >= MAX_IMAGES or size + len(data) > MAX_MEDIA_BYTES:
                            raise ValueError('image result exceeds per-message media limits')
                        count += 1
                        size += len(data)
                    except ValueError as exc:
                        reason = str(exc)
                content.append(TextBlock(f'[Image {block.media_type} was not supplied: {reason}.]') if reason else block)
            result.append(replace(message, content=content))
        else:
            result.append(message)
    return result
