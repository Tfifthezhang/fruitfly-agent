"""Pure completion data and selection state, independent of commands and I/O."""
from __future__ import annotations
from dataclasses import dataclass
from threading import RLock
from typing import Callable


@dataclass(frozen=True)
class CompletionQuery:
    text: str
    cursor: int


@dataclass(frozen=True)
class CompletionItem:
    label: str
    detail: str
    replacement: str


@dataclass(frozen=True)
class CompletionResult:
    start: int
    end: int
    items: tuple[CompletionItem, ...]


@dataclass(frozen=True)
class CompletionView:
    items: tuple[CompletionItem, ...] = ()
    selected: int = 0


CompletionProvider = Callable[[CompletionQuery], CompletionResult | None]


class CompletionState:
    """Own selection and dismissal; acceptance only returns a text replacement."""

    def __init__(self, provider: CompletionProvider) -> None:
        self.provider = provider
        self._result: CompletionResult | None = None
        self._selected = 0
        self._dismissed: CompletionQuery | None = None
        self._lock = RLock()

    @property
    def view(self) -> CompletionView:
        with self._lock:
            return CompletionView(self._result.items, self._selected) if self._result else CompletionView()

    def update(self, query: CompletionQuery) -> None:
        with self._lock:
            if query == self._dismissed:
                return
            self._dismissed = None
            previous = self._result.items[self._selected].replacement if self._result else None
            result = self.provider(query)
            if result is not None and not (0 <= result.start <= query.cursor <= result.end <= len(query.text)):
                raise ValueError('completion replacement range must contain the cursor')
            self._result = result if result is not None and result.items else None
            replacements = tuple(item.replacement for item in self._result.items) if self._result else ()
            self._selected = replacements.index(previous) if previous in replacements else 0

    def dismiss(self, query: CompletionQuery) -> None:
        with self._lock:
            self._result, self._selected, self._dismissed = None, 0, query

    def clear(self) -> None:
        with self._lock:
            self._result, self._selected, self._dismissed = None, 0, None

    def move(self, delta: int) -> bool:
        with self._lock:
            if self._result is None:
                return False
            self._selected = (self._selected + delta) % len(self._result.items)
            return True

    def accept(self, query: CompletionQuery) -> CompletionQuery | None:
        with self._lock:
            # Refresh against current registrations before using an earlier view.
            self.update(query)
            result = self._result
            if result is None:
                return None
            replacement = result.items[self._selected].replacement
            accepted = CompletionQuery(query.text[:result.start] + replacement + query.text[result.end:],
                                       result.start + len(replacement))
            self.dismiss(accepted)
            return accepted
