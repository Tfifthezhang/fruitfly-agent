"""Content-addressed text trees and fresh owned materialization directories."""
from pathlib import Path
import json
from fruitfly_agent.improvement.contracts.versions import StateSnapshot
from fruitfly_agent.improvement.contracts.versions import SnapshotFile


def capture_source_tree(root: Path) -> StateSnapshot:
    files = []
    for package in ("fruitfly_agent", "fruitfly_eval"):
        for path in sorted((root / package).rglob("*.py")):
            if "__pycache__" not in path.parts and not path.is_symlink():
                files.append(SnapshotFile(path.relative_to(root).as_posix(), path.read_text(encoding="utf-8")))
    for name in ("pyproject.toml", "README.md", "LICENSE", "THIRD_PARTY_NOTICES.md"):
        files.append(SnapshotFile(name, (root / name).read_text(encoding="utf-8")))
    return StateSnapshot(tuple(files), "immutable-source")


class SnapshotStore:
    def __init__(self, artifacts):
        self.artifacts = artifacts

    def put(self, snapshot: StateSnapshot) -> str:
        reference = self.artifacts.put_text(json.dumps(snapshot.to_dict(), ensure_ascii=False, sort_keys=True,
                                                     separators=(",", ":"))).artifact_id
        if reference != snapshot.snapshot_id:
            raise ValueError("state snapshot identity mismatch")
        return reference

    def read(self, reference: str) -> StateSnapshot:
        snapshot = StateSnapshot.from_dict(json.loads(self.artifacts.read_text(reference)))
        if snapshot.snapshot_id != reference:
            raise ValueError("snapshot failed content verification")
        return snapshot

    def materialize(self, reference: str, destination: Path) -> Path:
        snapshot = self.read(reference)
        if any(p.is_symlink() for p in (destination, *destination.parents)):
            raise ValueError("snapshot destination cannot use symlinks")
        destination.mkdir(parents=True, exist_ok=False)
        for entry in snapshot.files:
            path = destination / entry.path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(entry.content, encoding="utf-8")
        return destination
