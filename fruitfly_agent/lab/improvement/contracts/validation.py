"""Public validation contracts; no external effects."""
from __future__ import annotations
from pathlib import PurePosixPath
import re

def identifier(value: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', value):
        raise ValueError('a stable identifier is required')


def relative_path(value: str) -> None:
    if (not isinstance(value, str) or not value or '\\' in value
            or PurePosixPath(value).is_absolute() or any(p in {'', '.', '..'} for p in value.split('/'))
            or any(ord(c) < 32 for c in value)):
        raise ValueError('an owned relative file path is required')


def bounded(value: str, maximum=120_000, *, empty=False) -> None:
    if not isinstance(value, str) or len(value) > maximum or (not empty and not value.strip()):
        raise ValueError('text must fit its declared bound')

