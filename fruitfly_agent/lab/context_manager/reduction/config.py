"""Typed summarizing parameters: the only source of defaults."""

from dataclasses import dataclass
import math

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
    per_message_char_limit: int = 2000
    summary_attempts: int = 2
    summary_timeout_seconds: float = 60.0
    token_estimator: str = "heuristic_cjk"
    prompt_version: str = "continuity"

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
            or self.summary_timeout_seconds <= 0
        ):
            raise ValueError("summary_timeout_seconds must be finite and positive")
        from .estimate import resolve_token_estimator

        resolve_token_estimator(self.token_estimator)
        if self.prompt_version != "continuity":
            available = "continuity"
            raise ValueError(
                f"unknown summarizing prompt version {self.prompt_version!r}; "
                f"available: {available}"
            )


__all__ = ["SummarizingCompactorConfig"]
