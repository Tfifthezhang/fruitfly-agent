"""Structured image selections and their editable prompt positions."""
from __future__ import annotations

from dataclasses import dataclass
import re
import shlex
from typing import Callable

from fruitfly_agent.interactive.contracts.inputs import ImageAttachment, UserContent, TextBlock, image_input, normalize_input


@dataclass
class ImageItem:
    start: int
    end: int
    label: str
    image: ImageAttachment


class Composer:
    def __init__(self, loader: Callable[[str], ImageAttachment] | None,
                 clipboard: Callable[[], ImageAttachment | None] | None = None) -> None:
        self.loader = loader
        self.clipboard = clipboard
        self.text = ''
        self.items: list[ImageItem] = []
        self.serial = 0
        self.notice = ''

    @property
    def pending(self) -> bool:
        return bool(self.text or self.items)

    def clear(self) -> None:
        self.text = ''
        self.items.clear()
        self.notice = ''

    def release_command(self, text: str) -> None:
        if self.text == text:
            self.clear()

    def ranges(self) -> tuple[tuple[int, int], ...]:
        return tuple((v.start, v.end) for v in self.items)

    def update(self, text: str) -> None:
        self._sync(text)

    def _sync(self, text: str) -> None:
        old = self.text
        if old == text:
            return
        start = 0
        while start < min(len(old), len(text)) and old[start] == text[start]:
            start += 1
        tail = 0
        while tail < min(len(old), len(text)) - start and old[-tail - 1] == text[-tail - 1]:
            tail += 1
        end = len(old) - tail
        shift = len(text) - len(old)
        kept = []
        for item in self.items:
            if item.end <= start:
                kept.append(item)
            elif item.start >= end:
                item.start += shift
                item.end += shift
                kept.append(item)
        self.items = kept
        self.text = text

    def _insert(self, start: int, end: int, image: ImageAttachment, label: str) -> tuple[str, int]:
        normalize_input([*(v.image for v in self.items), image])
        self.serial += 1
        short = ''.join(c for c in label.rsplit('/', 1)[-1] if c.isprintable())[:40]
        token = f'[Image #{self.serial}] ({short})'
        self._sync(self.text[:start] + token + self.text[end:])
        self.items.append(ImageItem(start, start + len(token), label, image))
        self.items.sort(key=lambda v: v.start)
        return self.text, start + len(token)

    def transform(self, text: str, cursor: int) -> tuple[str, int]:
        self._sync(text)
        if self.loader is None or re.match(r'^/[a-z][a-z0-9_-]*(?:\s|$)', text.lstrip()) or '```' in text:
            return text, cursor
        # Only explicit @ references are recognized inside ordinary prose.
        pattern = r'''(?<!\S)@(?:"(?:\\.|[^"\\])*"|'[^']*'|(?:\\.|[^\s])+)'''
        matches = list(re.finditer(pattern, text))
        # Terminals may deliver drops as path text rather than bracketed paste.
        dropped = r'''(?<!\S)(?:"(?:/|~/|\./)(?:\\.|[^"\\])*"|'(?:/|~/|\./)[^']*'|(?:/|~/|\./)(?:\\.|[^\s])+)'''
        matches += [m for m in re.finditer(dropped, text)
                    if not any(m.start() < v.end() and m.end() > v.start() for v in matches)]
        matches.sort(key=lambda m: m.start())
        if not matches:
            # A complete standalone dropped path is also an explicit selection.
            try:
                values = shlex.split(text)
            except ValueError:
                return text, cursor
            if len(values) == 1 and self._image_path(values[0]) and ('/' in values[0] or text.startswith(('"', "'"))):
                matches = list(re.finditer(r'.+', text))
        for match in reversed(matches):
            if match is None or any(match.start() < v.end and match.end() > v.start for v in self.items):
                continue
            reference = match.group()
            try:
                path = shlex.split(reference[1:] if reference.startswith('@') else reference)[0]
                if not self._image_path(path):
                    continue
                image = self.loader(path)
                previous_end = match.end()
                _, replacement_end = self._insert(match.start(), previous_end, image, path)
                if cursor >= previous_end:
                    cursor += replacement_end - previous_end
                elif cursor > match.start():
                    cursor = replacement_end
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                self.notice = 'Image unavailable: ' + str(exc)
        return self.text, cursor

    @staticmethod
    def _image_path(path: str) -> bool:
        return path.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp'))

    def paste(self, text: str, cursor: int, payload: str) -> tuple[str, int]:
        self._sync(text)
        try:
            paths = shlex.split(payload)
        except ValueError:
            paths = []
        if paths and self.loader is not None and all(self._image_path(p) for p in paths) and '```' not in text:
            # Validate the complete drop before mutating the draft.
            try:
                images = [self.loader(path) for path in paths]
                normalize_input([*(v.image for v in self.items), *images])
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                self.notice = 'Image unavailable: ' + str(exc)
            else:
                for path, image in zip(paths, images):
                    _, cursor = self._insert(cursor, cursor, image, path)
                return self.text, cursor
        return self.transform(text[:cursor] + payload + text[cursor:], cursor + len(payload))

    def paste_image(self, text: str, cursor: int) -> tuple[str, int]:
        self._sync(text)
        try:
            image = self.clipboard() if self.clipboard is not None else None
            if image is None:
                self.notice = 'No clipboard image available; use @"local/image.png".'
                return self.text, cursor
            return self._insert(cursor, cursor, image, 'clipboard')
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            self.notice = 'Image unavailable: ' + str(exc)
            return self.text, cursor

    def prepare(self, text: str) -> UserContent:
        text, _ = self.transform(text or self.text, len(text or self.text))
        if self.notice:
            notice, self.notice = self.notice, ''
            raise ValueError(notice)
        # Markers only denote images when backed by actual selected items.
        content: list[TextBlock | ImageAttachment] = []
        cursor = 0
        for item in self.items:
            if item.start > cursor:
                content.append(TextBlock(text[cursor:item.start]))
            content.append(item.image)
            cursor = item.end
        if cursor < len(text):
            content.append(TextBlock(text[cursor:]))
        return normalize_input(content) if self.items else image_input(text, [])
