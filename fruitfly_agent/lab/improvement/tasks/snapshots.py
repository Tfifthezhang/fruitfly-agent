"""Atomic content-addressed task snapshots with corruption and path checks."""
import os
from pathlib import Path
import tempfile
from .packages import digest, encoded, safe_path

class TaskSnapshotStore:
    """Atomic content-addressed search receipts; rejects relocation and corruption."""
    def __init__(self, workspace: Path) -> None:
        self.workspace = Path(workspace).resolve()
        self.root = self.workspace / ".fruitfly/improvement/task-snapshots"

    def freeze(self, payload: object) -> tuple[Path, str]:
        data = encoded(payload)
        identity = digest(data)
        path = safe_path(self.workspace, self.root / (identity[7:] + ".json"))
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".snapshot-", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError:
                pass
            self.verify(path, identity)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return path, identity

    def verify(self, path: Path, identity: str) -> None:
        source = safe_path(self.workspace, path)
        if digest(source.read_bytes()) != identity:
            raise ValueError("improvement snapshot corrupted")


