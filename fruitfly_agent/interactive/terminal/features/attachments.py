"""Pending local attachments; command handlers never read files directly."""
from __future__ import annotations

import shlex
from typing import Callable

from fruitfly_agent.interactive.contracts.inputs import ImageAttachment, UserContent, normalize_input, image_input
from fruitfly_agent.interactive.contracts.commands import CommandResult, InteractiveCommand


class AttachmentDraft:
    def __init__(self, loader: Callable[[str], ImageAttachment] | None) -> None:
        self.loader = loader
        self.items: list[tuple[str, ImageAttachment]] = []
        self.text = ''

    @property
    def pending(self) -> bool:
        return bool(self.items or self.text)

    def clear(self) -> None:
        self.items.clear()
        self.text = ''

    def prepare(self, text: str) -> UserContent:
        self.text = text or self.text
        return image_input(self.text, [image for _, image in self.items])

    def attach(self, command: InteractiveCommand) -> CommandResult:
        try:
            paths = shlex.split(' '.join(command.arguments))
            if len(paths) != 1:
                raise ValueError('usage: /attach "LOCAL_IMAGE_PATH"')
            if self.loader is None:
                raise ValueError('this host does not provide local image attachments')
            image = self.loader(paths[0])
            normalize_input([*(item for _, item in self.items), image])
            self.items.append((paths[0], image))
            return CommandResult(text=f'Attached image {len(self.items)}: {paths[0]} ({image.media_type}). Submit a message or Enter to send.\n')
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            return CommandResult(text=f'cannot attach: {exc}\n')

    def show(self, command: InteractiveCommand) -> CommandResult:
        if command.arguments:
            return CommandResult(text='usage: /attachments\n')
        rows = [f'{i}. {path} ({image.media_type})' for i, (path, image) in enumerate(self.items, 1)]
        if self.text:
            rows.append('Unsent text: ' + self.text)
        return CommandResult(text='\n'.join(rows or ['No pending attachments.']) + '\n')

    def detach(self, command: InteractiveCommand) -> CommandResult:
        if command.arguments == ('all',):
            self.clear()
            return CommandResult(text='Pending attachments and unsent draft cleared.\n')
        try:
            if len(command.arguments) != 1:
                raise ValueError
            index = int(command.arguments[0]) - 1
            if index < 0 or index >= len(self.items):
                raise ValueError
            self.items.pop(index)
        except ValueError:
            return CommandResult(text='usage: /detach N | /detach all\n')
        return CommandResult(text='Attachment removed.\n')
