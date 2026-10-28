"""Typed summarizing parameters: the only source of defaults."""

from dataclasses import dataclass
import math
from .prompts import INSTRUCTIONS

@dataclass(frozen=True)
class SummarizingCompactorConfig:
    """Research parameters owned by this concrete algorithm."""

    enabled: bool = True
    reserve_tokens: int = 1024
    keep_recent_tokens: int = 20000
    reactive_keep_recent_tokens: int = 10000
    max_shrink_steps: int = 5
    summary_word_limit: int = 400
    summary_max_tokens: int = 2048
    history_char_limit: int = 120000
    per_message_char_limit: int = 120000
    summary_attempts: int = 2
    summary_timeout_seconds: float = 60.0
    token_estimator: str = "heuristic_cjk"
    prompt_version: str = "continuity"
    summary_instructions: str = INSTRUCTIONS
    trigger_ratio: float = 0.9
    max_pages: int = 64

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ValueError("enabled must be a boolean")
        non_negative = {"reserve_tokens": self.reserve_tokens}
        positive = {
            "keep_recent_tokens": self.keep_recent_tokens,
            "reactive_keep_recent_tokens": self.reactive_keep_recent_tokens,
            "max_shrink_steps": self.max_shrink_steps,
            "summary_word_limit": self.summary_word_limit,
            "summary_max_tokens": self.summary_max_tokens,
            "history_char_limit": self.history_char_limit,
            "per_message_char_limit": self.per_message_char_limit,
            "summary_attempts": self.summary_attempts,
            "max_pages": self.max_pages,
        }
        for name, value in non_negative.items():
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        for name, value in positive.items():
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be at least 1")
        if (
            isinstance(self.summary_timeout_seconds, bool)
            or not isinstance(self.summary_timeout_seconds, (int, float))
            or not math.isfinite(self.summary_timeout_seconds)
            or not 0 < self.summary_timeout_seconds <= 600
        ):
            raise ValueError("summary_timeout_seconds must be finite and within (0, 600]")
        from ....measurement.methods.heuristic.estimator import resolve_token_estimator

        resolve_token_estimator(self.token_estimator)
        if not isinstance(self.summary_instructions, str) or not 1 <= len(self.summary_instructions.strip()) <= 12000:
            raise ValueError('summary_instructions must contain 1 to 12000 characters')
        if isinstance(self.trigger_ratio, bool) or not isinstance(self.trigger_ratio, (int, float)) or not .1 <= self.trigger_ratio <= 1:
            raise ValueError('trigger_ratio must be between 0.1 and 1')
        if self.max_pages > 128 or self.summary_attempts > 8:
            raise ValueError('auxiliary pages/attempts exceed the supported bound')
        if self.prompt_version != "continuity":
            available = "continuity"
            raise ValueError(
                f"unknown summarizing prompt version {self.prompt_version!r}; "
                f"available: {available}"
            )


__all__ = ["SummarizingCompactorConfig"]
