"""Session-scoped immutable context artifacts for the RLM workspace."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time
from typing import Any


_REF = re.compile(r"^(?:context://sha256/)?([0-9a-f]{64})$")


@dataclass(frozen=True)
class ContextArtifact:
    artifact_id: str
    reference: str
    kind: str
    media_type: str
    size_bytes: int
    characters: int
    sha256: str
    origin: str
    created_at: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SessionArtifactStore:
    """Content-addressed text artifacts stored beside one Session.

    Each object and metadata record is published atomically.  There is no
    shared mutable index: listing scans the small metadata directory, so the
    host and its IPython child process cannot clobber one another.
    """

    def __init__(self, root: str | Path, *, max_artifact_bytes: int) -> None:
        self.root = Path(root).resolve()
        self.max_artifact_bytes = max_artifact_bytes
        if max_artifact_bytes < 1:
            raise ValueError("max_artifact_bytes must be positive")
        self.objects = self.root / "objects"
        self.metadata = self.root / "metadata"
        self.states = self.root / "states"
        for path in (self.objects, self.metadata, self.states):
            path.mkdir(parents=True, exist_ok=True)

    def put_text(
        self,
        text: str,
        *,
        kind: str = "context",
        media_type: str = "text/plain",
        origin: str = "runtime",
    ) -> ContextArtifact:
        if not isinstance(text, str):
            raise TypeError("artifact text must be a string")
        encoded = text.encode("utf-8")
        if len(encoded) > self.max_artifact_bytes:
            raise ValueError(
                f"artifact is {len(encoded)} bytes; limit is {self.max_artifact_bytes}"
            )
        digest = hashlib.sha256(encoded).hexdigest()
        object_path = self.objects / f"{digest}.txt"
        metadata_path = self.metadata / f"{digest}.json"
        artifact = ContextArtifact(
            artifact_id=digest,
            reference=f"context://sha256/{digest}",
            kind=str(kind),
            media_type=str(media_type),
            size_bytes=len(encoded),
            characters=len(text),
            sha256=digest,
            origin=str(origin),
            created_at=time.time(),
        )
        if not object_path.exists():
            self._atomic_write(object_path, encoded)
        if not metadata_path.exists():
            self._atomic_write(
                metadata_path,
                json.dumps(artifact.to_dict(), ensure_ascii=False, sort_keys=True).encode(
                    "utf-8"
                ),
            )
        return self.stat(artifact.reference)

    def stat(self, reference: str) -> ContextArtifact:
        digest = self._digest(reference)
        metadata_path = self.metadata / f"{digest}.json"
        object_path = self.objects / f"{digest}.txt"
        if not metadata_path.is_file() or not object_path.is_file():
            raise KeyError(f"unknown context artifact: {reference}")
        raw = json.loads(metadata_path.read_text(encoding="utf-8"))
        artifact = ContextArtifact(**raw)
        data = object_path.read_bytes()
        actual = hashlib.sha256(data).hexdigest()
        if actual != digest or artifact.sha256 != digest:
            raise ValueError(f"context artifact failed integrity check: {reference}")
        if len(data) != artifact.size_bytes:
            raise ValueError(f"context artifact size mismatch: {reference}")
        return artifact

    def read(self, reference: str, *, offset: int = 0, limit: int = 20_000) -> str:
        if offset < 0:
            raise ValueError("offset must be non-negative")
        if limit < 1:
            raise ValueError("limit must be positive")
        digest = self._digest(reference)
        self.stat(reference)
        text = (self.objects / f"{digest}.txt").read_text(encoding="utf-8")
        return text[offset : offset + limit]

    def search(
        self,
        reference: str,
        query: str,
        *,
        limit: int = 20,
        context_chars: int = 240,
    ) -> list[dict[str, Any]]:
        if not query:
            raise ValueError("query must not be empty")
        if limit < 1:
            raise ValueError("limit must be positive")
        digest = self._digest(reference)
        self.stat(reference)
        text = (self.objects / f"{digest}.txt").read_text(encoding="utf-8")
        lowered = text.casefold()
        needle = query.casefold()
        matches: list[dict[str, Any]] = []
        start = 0
        while len(matches) < limit:
            index = lowered.find(needle, start)
            if index < 0:
                break
            left = max(0, index - context_chars)
            right = min(len(text), index + len(query) + context_chars)
            matches.append(
                {
                    "offset": index,
                    "preview": text[left:right],
                    "preview_offset": left,
                }
            )
            start = index + max(1, len(query))
        return matches

    def list(self) -> list[ContextArtifact]:
        artifacts: list[ContextArtifact] = []
        for path in sorted(self.metadata.glob("*.json")):
            try:
                artifacts.append(self.stat(path.stem))
            except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
                continue
        return artifacts

    def save_state(self, name: str, value: Any) -> Path:
        path = self._state_path(name)
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
        if len(encoded) > self.max_artifact_bytes:
            raise ValueError(
                f"state is {len(encoded)} bytes; limit is {self.max_artifact_bytes}"
            )
        self._atomic_write(path, encoded)
        return path

    def load_state(self, name: str) -> Any:
        path = self._state_path(name)
        if not path.is_file():
            raise KeyError(f"unknown saved state: {name}")
        return json.loads(path.read_text(encoding="utf-8"))

    def list_states(self) -> list[str]:
        return sorted(path.stem for path in self.states.glob("*.json"))

    def _state_path(self, name: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", name):
            raise ValueError("state name must be a stable identifier")
        return self.states / f"{name}.json"

    @staticmethod
    def _digest(reference: str) -> str:
        match = _REF.fullmatch(reference.strip())
        if match is None:
            raise ValueError(f"invalid context reference: {reference!r}")
        return match.group(1)

    @staticmethod
    def _atomic_write(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, raw_tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        tmp = Path(raw_tmp)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp, path)
        except BaseException:
            try:
                tmp.unlink(missing_ok=True)
            finally:
                raise


class ContextWorkspace:
    """Small synchronous API preloaded into the IPython namespace."""

    def __init__(self, store: SessionArtifactStore) -> None:
        self._store = store

    def list(self) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self._store.list()]

    def stat(self, reference: str) -> dict[str, Any]:
        return self._store.stat(reference).to_dict()

    def read(self, reference: str, offset: int = 0, limit: int = 20_000) -> str:
        return self._store.read(reference, offset=offset, limit=limit)

    def search(
        self,
        reference: str,
        query: str,
        limit: int = 20,
        context_chars: int = 240,
    ) -> list[dict[str, Any]]:
        return self._store.search(
            reference,
            query,
            limit=limit,
            context_chars=context_chars,
        )

    def put(self, text: str, kind: str = "working", origin: str = "ipython") -> str:
        return self._store.put_text(text, kind=kind, origin=origin).reference

    def save_state(self, name: str, value: Any) -> str:
        return str(self._store.save_state(name, value))

    def load_state(self, name: str) -> Any:
        return self._store.load_state(name)

    def list_states(self) -> list[str]:
        return self._store.list_states()


__all__ = ["ContextArtifact", "ContextWorkspace", "SessionArtifactStore"]
