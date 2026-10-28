"""Freeze declared memory contents; trial copies never share production writes."""
from pathlib import Path
from fruitfly_agent.improvement.contracts.versions import SnapshotFile, StateSnapshot


class FileMemorySnapshots:
    def __init__(self, root: Path, workspace: Path):
        self.root = root
        self.workspace = workspace

    def freeze(self) -> StateSnapshot:
        if any(p.is_symlink() for p in (self.root, *self.root.parents)):
            raise ValueError("memory snapshot roots cannot use symlinks")
        root = self.root.resolve()
        workspace = self.workspace.resolve()
        root.relative_to(workspace)
        files = []
        if root.is_dir():
            for path in sorted(root.glob("*.md")):
                if path.is_symlink() or not path.is_file() or path.stat().st_size > 128000:
                    raise ValueError("memory snapshot needs regular bounded files")
                files.append(SnapshotFile(path.relative_to(workspace).as_posix(), path.read_text(encoding="utf-8")))
        return StateSnapshot(tuple(files), roots=(root.relative_to(workspace).as_posix(),))
