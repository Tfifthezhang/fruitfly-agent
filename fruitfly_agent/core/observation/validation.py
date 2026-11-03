"""Small source-neutral validation rules for public operation records."""
from __future__ import annotations

import math
import hashlib
import re

_IDENTIFIER = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,159}$')


def identifier(value: str, *, optional: bool = False) -> str:
    if not isinstance(value, str) or not (optional and not value or _IDENTIFIER.fullmatch(value)):
        raise ValueError('observation identifier must be bounded plain text')
    return value


def seconds(value: float) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError('observation seconds must be finite and nonnegative')
    return float(value)


def observed_identifier(value: str, *, optional: bool = False) -> str:
    """Bound untrusted correlation IDs without rejecting otherwise valid work."""
    try:
        return identifier(value, optional=optional)
    except ValueError:
        text = value if isinstance(value, str) else type(value).__name__
        return 'opaque-' + hashlib.sha256(text.encode('utf-8', errors='replace')).hexdigest()
