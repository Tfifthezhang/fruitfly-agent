"""Token estimation — cheap, conservative, research-swappable.

Conservative character heuristic for CJK text: CJK chars count as 1 token, other
chars as chars/4. Researchers can plug their own estimator through each
algorithm's configuration.
"""

from __future__ import annotations

import json
import math
from typing import Callable

from fruitfly_agent.core.data_model import (
    AgentMessage,
    AssistantMessage,
    CustomMessage,
    ImageBlock,
    TextBlock,
    ToolResultMessage,
    UserMessage,
)

_CJK_RANGES = (
    (0x4E00, 0x9FFF),  # CJK Unified
    (0x3400, 0x4DBF),  # Extension A
    (0x3000, 0x303F),  # CJK punctuation
    (0xFF00, 0xFFEF),  # fullwidth forms
    (0x3040, 0x30FF),  # kana
    (0xAC00, 0xD7AF),  # hangul
)


def count_cjk_chars(text: str) -> int:
    return sum(1 for c in text if any(lo <= ord(c) <= hi for lo, hi in _CJK_RANGES))


def estimate_tokens(text: str) -> int:
    """chars/4 heuristic with CJK chars counting as one token each."""
    cjk = count_cjk_chars(text)
    other = len(text) - cjk
    return math.ceil(cjk + other / 4)


def estimate_tokens_chars_div_4(text: str) -> int:
    """Original language-agnostic chars/4 heuristic."""

    return math.ceil(len(text) / 4)


TOKEN_ESTIMATORS = (
    "heuristic_cjk",
    "chars_div_4",
)


def resolve_token_estimator(name: str) -> Callable[[str], int]:
    """Resolve a serializable estimator ID without arbitrary imports."""

    if name == "heuristic_cjk":
        return estimate_tokens
    if name == "chars_div_4":
        return estimate_tokens_chars_div_4
    available = ", ".join(TOKEN_ESTIMATORS)
    raise ValueError(f"unknown token estimator {name!r}; available: {available}")


IMAGE_TOKENS = 1200  # Fixed estimate; actual image token usage is model-specific.


def estimate_message_tokens(
    message: AgentMessage,
    estimate_text: Callable[[str], int] = estimate_tokens,
) -> int:
    if isinstance(message, UserMessage):
        if isinstance(message.content, str):
            return estimate_text(message.content)
        total = 0
        for block in message.content:
            if isinstance(block, TextBlock):
                total += estimate_text(block.text)
            elif isinstance(block, ImageBlock):
                total += IMAGE_TOKENS
        return total
    if isinstance(message, AssistantMessage):
        total = 0
        for block in message.content:
            if isinstance(block, TextBlock):
                total += estimate_text(block.text)
            elif hasattr(block, "thinking"):
                total += estimate_text(block.thinking)
            elif hasattr(block, "name") and hasattr(block, "input"):
                total += estimate_text(block.name + json.dumps(block.input, ensure_ascii=False))
        return total
    if isinstance(message, ToolResultMessage):
        return sum(estimate_text(b.text) for b in message.content if isinstance(b, TextBlock))
    if isinstance(message, CustomMessage):
        return estimate_text(message.text)
    return 0


__all__ = [
    "estimate_tokens",
    "estimate_tokens_chars_div_4",
    "estimate_message_tokens",
    "resolve_token_estimator",
    "TOKEN_ESTIMATORS",
    "count_cjk_chars",
    "IMAGE_TOKENS",
]
