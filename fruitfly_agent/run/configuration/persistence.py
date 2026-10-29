"""Atomic byte persistence for configuration and credential operations."""
import os
from pathlib import Path
import tempfile
from contextlib import contextmanager
from collections.abc import Iterable, Iterator, Mapping


class FileTransaction:
    """Guard prepared inputs and restore owned files after a failed commit."""

    def __init__(self, paths: Mapping[Path, bytes | None]) -> None:
        self.originals = dict(paths)

    @classmethod
    def capture(cls, paths: Iterable[Path]) -> 'FileTransaction':
        return cls({path: path.read_bytes() if path.exists() else None for path in paths})

    @contextmanager
    def writing(self, paths: Iterable[Path]) -> Iterator[None]:
        for path, original in self.originals.items():
            current = path.read_bytes() if path.exists() else None
            if current != original:
                raise ValueError('configuration changed while preparing; reopen configuration and retry')
        try:
            yield
        except BaseException:
            for path in reversed(tuple(paths)):
                original = self.originals[path]
                if original is None:
                    path.unlink(missing_ok=True)
                elif not path.exists() or path.read_bytes() != original:
                    write_bytes(path, original)
            raise


def write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)

