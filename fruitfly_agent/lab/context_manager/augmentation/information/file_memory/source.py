"""Workspace Markdown memory source."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from ..lexical import LexicalRetriever
from ..models import InformationArtifact, InformationHit, InformationQuery, InformationRef, InformationSpaceDescriptor
from ..spaces import InformationSpace


class FileMemorySource:
    """Read a small, editable MEMORY.md index and sibling topic notes."""

    space_id = "workspace-memory"

    def __init__(self, root: Path, *, index_max_chars: int = 2_000) -> None:
        self.root = root.resolve()
        self.index_max_chars = index_max_chars

    def artifacts(self) -> Sequence[InformationArtifact]:
        index = self.root / "MEMORY.md"
        index_text = self._read(index, self.index_max_chars)
        items = [self._artifact("MEMORY.md", f"Index: {index}\n" + (index_text or "(empty index)"))]
        if not self.root.is_dir():
            return tuple(items)
        for path in sorted(self.root.glob("*.md"))[:128]:
            if path.name == "MEMORY.md":
                continue
            content = self._read(path, 16_000)
            if content:
                items.append(self._artifact(path.name, content))
        return tuple(items)

    def get(self, ref: InformationRef) -> InformationArtifact | None:
        if ref.space_id != self.space_id:
            return None
        return next((item for item in self.artifacts() if item.ref == ref), None)

    def _read(self, path: Path, limit: int) -> str:
        if not path.is_file() or not path.resolve().is_relative_to(self.root):
            return ""
        if path.stat().st_size > 128_000:
            return ""
        return path.read_text(encoding="utf-8", errors="replace")[:limit].strip()

    def _artifact(self, name: str, text: str) -> InformationArtifact:
        path = self.root / name
        return InformationArtifact(
            ref=InformationRef(self.space_id, name),
            payload=text,
            provenance={"path": str(path), "source": "workspace-memory"},
            updated_at=path.stat().st_mtime if path.exists() else 0.0,
        )


class FileMemoryRetriever:
    space_id = FileMemorySource.space_id

    def __init__(self, source: FileMemorySource) -> None:
        self.source = source
        self.lexical = LexicalRetriever(self.space_id, source)

    async def retrieve(self, query: InformationQuery) -> Sequence[InformationHit]:
        if query.space_ids and self.space_id not in query.space_ids:
            return ()
        index = self.source.artifacts()[0]
        matches = await self.lexical.retrieve(query)
        return (InformationHit(index, 3.0),) + tuple(
            hit for hit in matches if hit.artifact.ref != index.ref
        )


def create_file_memory_space(root: Path) -> InformationSpace:
    source = FileMemorySource(root)
    return InformationSpace(
        descriptor=InformationSpaceDescriptor(
            source.space_id, "Workspace memory", persistent=True, writable=True
        ),
        reader=source,
        retriever=FileMemoryRetriever(source),
    )
