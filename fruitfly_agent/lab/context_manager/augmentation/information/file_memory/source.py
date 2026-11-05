"""Frozen cross-session memory directory with on-demand document reads."""
from pathlib import Path
from ..models import InformationArtifact, InformationHit, InformationQuery, InformationRef, InformationSpaceDescriptor
from ..spaces import InformationSpace
from .validation import validate_memories
from .methods.indexed_notes.catalog import render_catalog


class FileMemorySource:
    space_id = 'workspace-memory'

    def __init__(self, root: Path, *, entries=(), locations=None, index_max_chars=4000):
        self.root = root.resolve()
        self.entries = validate_memories(list(entries))
        self.locations = locations or {e['id']: str(self.root / (e['id'] + '.md')) for e in self.entries}
        text = render_catalog(self.entries, self.locations, max_chars=index_max_chars)
        self.index = InformationArtifact(InformationRef(self.space_id, 'MEMORY.md'), text,
            provenance={'source': self.space_id, 'path': str(self.root)})

    def artifacts(self):
        return (self.index,)

    def get(self, ref: InformationRef):
        if ref == self.index.ref:
            return self.index
        from fruitfly_agent.improvement.contracts.versions import canonical_json
        if ref.space_id == self.space_id:
            for entry in self.entries:
                if ref.artifact_id == entry['id']:
                    return InformationArtifact(ref, canonical_json(entry), provenance={'source': self.space_id})
        return None


class FileMemoryRetriever:
    space_id = FileMemorySource.space_id

    def __init__(self, source):
        self.source = source

    async def retrieve(self, query: InformationQuery):
        if query.space_ids and self.space_id not in query.space_ids:
            return ()
        return (InformationHit(self.source.index, 3.0),)


def create_file_memory_space(root: Path, *, entries=(), locations=None, index_max_chars=4000):
    source = FileMemorySource(root, entries=entries, locations=locations, index_max_chars=index_max_chars)
    return InformationSpace(InformationSpaceDescriptor(source.space_id, 'Cross-session memory', persistent=True,
        writable=False), reader=source, retriever=FileMemoryRetriever(source))
