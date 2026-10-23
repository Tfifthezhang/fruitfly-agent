"""Keep one locked writer while idle runtimes replace their session binding."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from fruitfly_agent.core.session.storage import Session


@dataclass
class SessionLease:
    session: Session
    shared: bool
    release: Callable[[], None]


class SessionLeases:
    """Reference counting only; Application serializes runtime replacement."""

    def __init__(self) -> None:
        self.writers: dict[Path, tuple[Session, int]] = {}

    def acquire(self, path: Path, *, resume: bool) -> SessionLease:
        key = path.resolve()
        existing = self.writers.get(key)
        if existing is not None and not resume:
            raise ValueError("session is already open; continuing it requires recovery")
        writer, count = existing if existing is not None else (Session(path), 0)
        self.writers[key] = writer, count + 1
        released = False

        def release() -> None:
            nonlocal released
            if released:
                return
            released = True
            session, references = self.writers[key]
            if references == 1:
                del self.writers[key]
                session.close()
            else:
                self.writers[key] = session, references - 1

        return SessionLease(writer, count > 0, release)
