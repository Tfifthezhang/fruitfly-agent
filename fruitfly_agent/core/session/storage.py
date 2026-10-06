"""Durable session storage as an append-only JSONL entry tree.

Correctness invariants (all load-time enforced, torn writes recovered):
- one global id sequence across every entry, strictly consecutive from 1;
- ids unique; parentId is None or references an existing earlier entry;
- append is idempotent by explicit id (provisioned ids);
- torn tail (last line is a JSON syntax error) → discarded, valid prefix kept;
- a file missing its trailing newline is repaired on next append;
- one writer per session file: flock held for the session's lifetime.
"""

from __future__ import annotations

import fcntl
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..errors import SessionCorruptError
from ..data_model.context import ContextItem
from ..data_model.messages import AgentMessage, message_from_dict


@dataclass(frozen=True)
class SessionEntry:
    id: int
    parent_id: int | None
    type: str  # "message" | "compaction" | "meta"
    timestamp: float
    payload: dict[str, Any]

    def to_json_line(self) -> str:
        return (
            json.dumps(
                {
                    "id": self.id,
                    "parentId": self.parent_id,
                    "type": self.type,
                    "timestamp": self.timestamp,
                    **self.payload,
                },
                ensure_ascii=False,
            )
            + "\n"
        )


class Session:
    """Append-only session log. Holds an exclusive flock for its lifetime."""

    def __init__(self, path: str | Path, *, lane: str = "main") -> None:
        self.path = Path(path)
        self.lane = lane
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_file = self.path.with_suffix(self.path.suffix + ".lock")
        self._lock_fd = open(self._lock_file, "a+b")  # noqa: SIM115 — held for lifetime
        try:
            fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self._lock_fd.close()
            raise SessionCorruptError(
                f"session {self.path} is locked by another process: {exc}"
            ) from exc
        self._entries: list[SessionEntry] = []
        self._repair_newline = False
        try:
            self._load()
        except BaseException:
            # Construction did not complete, so __exit__/close cannot run.
            try:
                fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
            except OSError:
                pass
            self._lock_fd.close()
            raise

    # -- load / validation --------------------------------------------------

    def _load(self) -> None:
        if not self.path.exists():
            return
        raw = self.path.read_bytes()
        if not raw:
            return
        if not raw.endswith(b"\n"):
            # Missing trailing newline: repair on the next append.
            self._repair_newline = True
        text = raw.decode("utf-8", errors="replace")
        lines = text.split("\n")
        last_non_empty = max(
            (i for i, line in enumerate(lines) if line.strip()), default=-1
        )
        entries: list[SessionEntry] = []
        torn = 0
        for i, line in enumerate(lines):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                if i == last_non_empty:
                    # Torn tail: an unacknowledged append. Keep the valid prefix.
                    torn = 1
                    break
                raise SessionCorruptError(
                    f"session {self.path}: invalid JSON on line {i + 1} (not a torn tail)"
                ) from None
            entries.append(self._parse_entry(obj, i + 1))
        if torn:
            self._rewrite_valid_prefix(entries)
        self._entries = entries
        self._validate(entries)

    @staticmethod
    def _parse_entry(obj: Any, line_no: int) -> SessionEntry:
        if not isinstance(obj, dict):
            raise SessionCorruptError(f"session line {line_no}: entry is not an object")
        try:
            entry_id = int(obj["id"])
            parent_id = obj.get("parentId")
            parent_id = int(parent_id) if parent_id is not None else None
        except (KeyError, TypeError, ValueError) as exc:
            raise SessionCorruptError(f"session line {line_no}: bad id/parentId: {exc}") from exc
        entry_type = str(obj.get("type") or "message")
        if entry_type not in ("message", "compaction", "meta"):
            raise SessionCorruptError(
                f"session line {line_no}: unknown entry type {entry_type!r}"
            )
        payload = {k: v for k, v in obj.items() if k not in ("id", "parentId", "type", "timestamp")}
        return SessionEntry(
            id=entry_id,
            parent_id=parent_id,
            type=entry_type,
            timestamp=float(obj.get("timestamp") or 0.0),
            payload=payload,
        )

    @staticmethod
    def _validate(entries: list[SessionEntry]) -> None:
        seen: set[int] = set()
        expected = 1
        for entry in entries:
            if entry.id != expected:
                raise SessionCorruptError(
                    f"session: non-consecutive id sequence (expected {expected}, got {entry.id})"
                )
            if entry.id in seen:
                raise SessionCorruptError(f"session: duplicate entry id {entry.id}")
            seen.add(entry.id)
            if entry.parent_id is not None and (
                entry.parent_id >= entry.id or entry.parent_id not in seen
            ):
                raise SessionCorruptError(
                    f"session: entry {entry.id} has invalid parentId {entry.parent_id}"
                )
            expected += 1

    def _rewrite_valid_prefix(self, entries: list[SessionEntry]) -> None:
        """Atomically re-publish the valid prefix after a torn tail."""
        tmp = self.path.with_name(self.path.name + ".repair")
        with open(tmp, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(entry.to_json_line())
        os.replace(tmp, self.path)

    # -- append ---------------------------------------------------------------

    def append(
        self,
        type: str,
        payload: dict[str, Any],
        *,
        parent_id: int | None = None,
        entry_id: int | None = None,
        sync: bool = False,
    ) -> SessionEntry:
        """Append an entry. Idempotent when entry_id is given and already exists."""
        if entry_id is not None:
            for existing in self._entries:
                if existing.id == entry_id:
                    return existing
        next_id = entry_id if entry_id is not None else (self._entries[-1].id + 1 if self._entries else 1)
        if self._entries and next_id != self._entries[-1].id + 1:
            raise SessionCorruptError(
                f"session: non-consecutive append (last {self._entries[-1].id}, got {next_id})"
            )
        entry = SessionEntry(
            id=next_id,
            parent_id=parent_id,
            type=type,
            timestamp=time.time(),
            payload=payload,
        )
        line = entry.to_json_line()
        if self._repair_newline:
            with self.path.open("ab") as f:
                f.write(b"\n")
            self._repair_newline = False
        with self.path.open("ab") as f:
            f.write(line.encode("utf-8"))
            f.flush()
            if sync:
                os.fsync(f.fileno())
        self._entries.append(entry)
        return entry

    # -- reads ----------------------------------------------------------------

    def read_all(self) -> list[SessionEntry]:
        return list(self._entries)

    def tail(self, n: int = 100) -> list[SessionEntry]:
        return self._entries[-n:]

    def messages(self) -> list[AgentMessage]:
        """Return the latest committed model projection plus newer messages.

        New entries store an algorithm-neutral ``messages`` projection.  The
        legacy summary/retainedTail shape remains readable for old sessions.
        """
        from ..data_model.messages import CUSTOM_KIND_COMPACTION, CustomMessage

        latest_compaction: SessionEntry | None = None
        for entry in self._entries:
            if entry.type == "compaction":
                latest_compaction = entry
        if latest_compaction is not None:
            payload = latest_compaction.payload
            projected: list[AgentMessage] = []
            raw_projection = payload.get("messages")
            if raw_projection is not None:
                if not isinstance(raw_projection, list):
                    raise SessionCorruptError("compaction messages is not a list")
                for m in raw_projection:
                    if not isinstance(m, dict):
                        raise SessionCorruptError("compaction messages entry is not an object")
                    projected.append(message_from_dict(m))
            else:
                summary = CustomMessage(
                    kind=CUSTOM_KIND_COMPACTION,
                    text=payload.get("summary") or "",
                    timestamp=latest_compaction.timestamp,
                )
                projected.append(summary)
                for m in payload.get("retainedTail") or []:
                    if not isinstance(m, dict):
                        raise SessionCorruptError(
                            "compaction retainedTail entry is not an object"
                        )
                    projected.append(message_from_dict(m))
            appended: list[AgentMessage] = []
            for entry in self._entries:
                if entry.id <= latest_compaction.id or entry.type != "message":
                    continue
                message = entry.payload.get("message")
                if not isinstance(message, dict):
                    raise SessionCorruptError(
                        f"session entry {entry.id}: missing message payload"
                    )
                appended.append(message_from_dict(message))
            return [*projected, *appended]
        return self.canonical_messages()

    def canonical_messages(self) -> list[AgentMessage]:
        """Return every original message entry, ignoring model projections."""

        return [item.message for item in self.context_items()]

    def context_items(self) -> list[ContextItem]:
        """Return canonical transcript items with durable session-entry IDs."""

        out: list[ContextItem] = []
        for entry in self._entries:
            if entry.type != "message":
                continue
            message = entry.payload.get("message")
            if not isinstance(message, dict):
                raise SessionCorruptError(f"session entry {entry.id}: missing message payload")
            out.append(ContextItem(id=f"session:{entry.id}", message=message_from_dict(message)))
        return out

    def close(self) -> None:
        try:
            fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
        except OSError:
            pass
        self._lock_fd.close()

    def __enter__(self) -> "Session":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
