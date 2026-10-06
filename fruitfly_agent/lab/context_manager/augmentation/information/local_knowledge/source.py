"""Local Markdown and text knowledge source."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from ..lexical import LexicalRetriever
from ..models import InformationArtifact, InformationRef, InformationSpaceDescriptor
from ..spaces import InformationSpace


class LocalKnowledgeSource:
    """Search current Markdown/text documents; files remain the source of truth."""

    space_id = "workspace-knowledge"

    def __init__(self, root: Path, *, chunk_chars: int = 1_500) -> None:
        self.root = root.resolve()
        self.chunk_chars = chunk_chars

    def artifacts(self) -> Sequence[InformationArtifact]:
        if not self.root.is_dir():
            return ()
        items: list[InformationArtifact] = []
        paths = sorted(
            path for path in self.root.rglob("*")
            if path.suffix.lower() in {".md", ".txt"}
            and not any(part.startswith(".") for part in path.relative_to(self.root).parts)
        )
        for path in paths[:256]:
            if not path.is_file() or not path.resolve().is_relative_to(self.root):
                continue
            if path.stat().st_size > 1_000_000:
                continue
            relative = path.relative_to(self.root).as_posix()
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            start, chunk, length = 1, [], 0
            for number, line in enumerate(lines, 1):
                if chunk and length + len(line) + 1 > self.chunk_chars:
                    items.append(self._artifact(path, relative, start, number - 1, chunk))
                    start, chunk, length = number, [], 0
                if len(line) > self.chunk_chars:
                    for part, offset in enumerate(range(0, len(line), self.chunk_chars), 1):
                        items.append(self._artifact(
                            path, relative, number, number,
                            [line[offset:offset + self.chunk_chars]], part=part,
                        ))
                    start = number + 1
                    continue
                chunk.append(line)
                length += len(line) + 1
            if chunk:
                items.append(self._artifact(path, relative, start, len(lines), chunk))
        return tuple(items)

    def get(self, ref: InformationRef) -> InformationArtifact | None:
        if ref.space_id != self.space_id:
            return None
        return next((item for item in self.artifacts() if item.ref == ref), None)

    def _artifact(
        self, path: Path, relative: str, start: int, end: int, lines: list[str],
        *, part: int | None = None,
    ) -> InformationArtifact:
        return InformationArtifact(
            ref=InformationRef(self.space_id, f"{relative}#L{start}" + (f"-P{part}" if part else "")),
            payload=f"Source: {path}:{start}-{end}\n" + "\n".join(lines),
            provenance={"path": str(path), "start_line": start, "end_line": end},
            updated_at=path.stat().st_mtime,
        )


def create_local_knowledge_space(root: Path) -> InformationSpace:
    source = LocalKnowledgeSource(root)
    return InformationSpace(
        descriptor=InformationSpaceDescriptor(
            source.space_id, "Local knowledge", persistent=True
        ),
        reader=source,
        retriever=LexicalRetriever(source.space_id, source),
    )
