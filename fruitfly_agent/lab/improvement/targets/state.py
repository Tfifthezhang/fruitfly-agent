"""Bounded snapshots for registered workspace text dependencies."""
from pathlib import Path
from fruitfly_agent.improvement.contracts.versions import SnapshotFile, StateSnapshot


class WorkspaceTextSnapshots:
    def __init__(self, root: Path, workspace: Path, *, recursive=True, suffixes=(".md", ".txt"), max_bytes=1000000):
        self.root, self.workspace = root, workspace
        self.recursive, self.suffixes, self.max_bytes = recursive, suffixes, max_bytes

    def freeze(self):
        root, workspace = self.root.resolve(), self.workspace.resolve()
        root.relative_to(workspace)
        if any(p.is_symlink() for p in (self.root, *self.root.parents)):
            raise ValueError("registered state roots cannot use symlinks")
        files: list[SnapshotFile] = []
        if root.exists():
            for path in sorted(root.rglob("*") if self.recursive else root.glob("*")):
                if path.is_symlink():
                    raise ValueError("state snapshots cannot contain symlinks")
                if path.is_file() and path.suffix.lower() in self.suffixes:
                    if path.stat().st_size > self.max_bytes or len(files) >= 512:
                        raise ValueError("registered state exceeds snapshot bounds")
                    files.append(SnapshotFile(path.relative_to(workspace).as_posix(), path.read_text(encoding="utf-8")))
        return StateSnapshot(tuple(files), roots=(root.relative_to(workspace).as_posix(),))
