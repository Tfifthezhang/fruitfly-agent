"""Operation results and tagged exceptions for runtime failure handling.

Environment operations return Result. Tools may raise ordinary exceptions;
Core converts them into error tool results. Providers raise tagged exceptions:
adapters handle bounded transient retries, and Core handles context overflow
or returns a terminal failure. Task cancellation propagates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, TypeVar

T = TypeVar("T")


class TaggedError(Exception):
    """Base exception with a machine-readable tag."""

    tag: str = "tagged"

    def __init__(self, message: str, *, details: Any = None) -> None:
        super().__init__(message)
        self.details = details


class OverflowError(TaggedError):
    """Context capacity failure; Core may retry after bounded reduction."""

    tag = "context_overflow"


class RetryableError(TaggedError):
    """Transient Provider failure; adapters may retry within configured limits."""

    tag = "retryable"


class FatalError(TaggedError):
    """Provider failure that cannot be retried or compacted away."""

    tag = "fatal"


class SessionCorruptError(TaggedError):
    """The session log violates the single-writer invariants."""

    tag = "session_corrupt"


class ValidationError(TaggedError):
    """Tool argument validation failed (converted to an error tool result)."""

    tag = "validation"


@dataclass(frozen=True)
class Result(Generic[T]):
    """Operation outcome containing a value or an error string."""

    ok: bool
    value: T | None = None
    error: str | None = None

    @classmethod
    def success(cls, value: T) -> "Result[T]":
        return cls(ok=True, value=value)

    @classmethod
    def failure(cls, error: str) -> "Result[T]":
        return cls(ok=False, error=error)

    @property
    def is_ok(self) -> bool:
        return self.ok

    def unwrap(self) -> T:
        """Return the value, or raise RuntimeError for a failed operation."""
        if not self.ok:
            raise RuntimeError(f"unwrap on error result: {self.error}")
        return self.value  # type: ignore[return-value]
