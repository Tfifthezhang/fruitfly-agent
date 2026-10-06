"""Path normalization and Unicode variant fallback.

macOS filename quirks that bite real agents: NFD normalization, curly
apostrophes, full-width spaces, and narrow no-break spaces in "AM/PM" names.
"""

from __future__ import annotations

import re
import unicodedata

from fruitfly_agent.core.env import ExecutionEnv

_UNICODE_SPACES = "  -   　"
_NARROW_NO_BREAK_SPACE = " "
_TRANSLATION = str.maketrans({ord(c): " " for c in _UNICODE_SPACES})


def normalize_tool_path(path: str) -> str:
    """Unicode spaces → ASCII space; strip a leading '@' (model quirk)."""
    normalized = path.translate(_TRANSLATION)
    if normalized.startswith("@"):
        normalized = normalized[1:]
    return normalized


def _narrow_ampm_variant(path: str) -> str:
    return re.sub(
        r" (AM|PM)\.",
        rf"{_NARROW_NO_BREAK_SPACE}\1.",
        path,
        flags=re.IGNORECASE,
    )


def resolve_read_path(env: ExecutionEnv, path: str) -> str:
    """Resolve with Unicode variants tried in order (first existing wins)."""
    normalized = normalize_tool_path(path)
    base = env.absolute_path(normalized)
    if not base.is_ok:
        return normalized
    resolved = base.unwrap()
    variants = [
        resolved,
        _narrow_ampm_variant(resolved),
        unicodedata.normalize("NFD", resolved),
        resolved.replace("'", "’"),
        unicodedata.normalize("NFD", resolved).replace("'", "’"),
    ]
    seen: set[str] = set()
    for variant in variants:
        if variant in seen:
            continue
        seen.add(variant)
        exists = env.exists(variant)
        if exists.is_ok and exists.unwrap():
            return variant
    return resolved
