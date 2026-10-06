"""Immutable, content-addressed text artifacts used by resolved runtimes."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import tempfile


_ARTIFACT_ID = re.compile(r"^sha256:[0-9a-f]{64}$")



@dataclass(frozen=True)
class DataArtifactRef:
    """Stable reference to UTF-8 content stored by :class:`DataArtifactStore`."""

    artifact_id: str
    media_type: str
    size_bytes: int

    def __post_init__(self) -> None:
        if not _ARTIFACT_ID.fullmatch(self.artifact_id):
            raise ValueError("artifact_id must be a sha256 content identifier")
        if not isinstance(self.media_type, str) or not self.media_type.strip():
            raise ValueError("media_type must be a non-empty string")
        if (
            isinstance(self.size_bytes, bool)
            or not isinstance(self.size_bytes, int)
            or self.size_bytes < 0
        ):
            raise ValueError("size_bytes must be a non-negative integer")

    def to_dict(self) -> dict[str, str | int]:
        return {
            "id": self.artifact_id,
            "media_type": self.media_type,
            "size_bytes": self.size_bytes,
        }


class DataArtifactStore:
    """Persist immutable UTF-8 text under its SHA-256 identity.

    The store never overwrites content. It is deliberately a Run capability so
    Lab algorithms receive only explicit read/write callbacks during assembly.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    def put_text(self, content: str) -> DataArtifactRef:
        if not isinstance(content, str):
            raise TypeError("artifact content must be text")
        encoded = content.encode("utf-8")
        artifact_id = "sha256:" + hashlib.sha256(encoded).hexdigest()
        path = self._path(artifact_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".artifact-", dir=path.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError:
                if path.is_symlink():
                    raise ValueError(f"data artifact must not be a symlink: {artifact_id}")
                if path.read_bytes() != encoded:
                    raise ValueError(
                        f"artifact content does not match identity {artifact_id}"
                    )
        finally:
            temporary.unlink(missing_ok=True)
        return DataArtifactRef(artifact_id, "text/plain; charset=utf-8", len(encoded))

    def read_text(self, artifact_id: str) -> str:
        path = self._path(artifact_id)
        if path.is_symlink():
            raise ValueError(f"data artifact must not be a symlink: {artifact_id}")
        try:
            encoded = path.read_bytes()
        except FileNotFoundError as exc:
            raise ValueError(f"data artifact is unavailable: {artifact_id}") from exc
        actual_id = "sha256:" + hashlib.sha256(encoded).hexdigest()
        if actual_id != artifact_id:
            raise ValueError(f"data artifact failed its content hash check: {artifact_id}")
        try:
            return encoded.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(
                f"data artifact is not valid UTF-8 text: {artifact_id}"
            ) from exc

    def list_text_ids(self, *, limit: int = 100) -> tuple[str, ...]:
        """List local, verified UTF-8 candidates without following arbitrary paths."""
        if not self.root.is_dir():
            return ()
        found: list[str] = []
        for path in sorted(self.root.iterdir()):
            artifact_id = "sha256:" + path.name
            if path.is_symlink() or not path.is_file() or not _ARTIFACT_ID.fullmatch(artifact_id):
                continue
            try:
                self.read_text(artifact_id)
            except ValueError:
                continue
            found.append(artifact_id)
            if len(found) >= limit:
                break
        return tuple(found)

    def _path(self, artifact_id: str) -> Path:
        if not isinstance(artifact_id, str) or not _ARTIFACT_ID.fullmatch(artifact_id):
            raise ValueError("artifact_id must be a sha256 content identifier")
        return self.root / artifact_id.removeprefix("sha256:")


__all__ = [
    "DataArtifactRef",
    "DataArtifactStore",
]
