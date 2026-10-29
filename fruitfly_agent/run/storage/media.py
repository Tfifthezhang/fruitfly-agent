"""Session-granted immutable media over the ordinary artifact store."""
from __future__ import annotations

from fruitfly_agent.core.extensions.protocols import SessionLike
from .artifacts import DataArtifactStore, DataArtifactRef


class SessionMedia:
    def __init__(self, store: DataArtifactStore, session: SessionLike) -> None:
        self.store, self.session = store, session
        self.grants: set[str] = set()
        for entry in session.read_all():
            if entry.type == 'meta' and entry.payload.get('kind') == 'mediaResource':
                record = entry.payload
                if not {'resource_id', 'media_type', 'size_bytes', 'origin'} <= record.keys():
                    raise ValueError('media resource record is incomplete')
                if not isinstance(record['origin'], str) or not record['origin']:
                    raise ValueError('media resource origin must be nonempty text')
                ref = DataArtifactRef(record['resource_id'], record['media_type'], record['size_bytes'])
                data = store.read_bytes(ref.artifact_id)
                if len(data) != ref.size_bytes:
                    raise ValueError('media resource size differs from the recorded size')
                self.grants.add(ref.artifact_id)

    def put(self, data: bytes, media_type: str, origin: str) -> str:
        ref = self.store.put_bytes(data, media_type=media_type)
        if ref.artifact_id not in self.grants:
            self.session.append('meta', {'kind': 'mediaResource', 'resource_id': ref.artifact_id,
                'media_type': media_type, 'size_bytes': len(data), 'origin': origin})
            self.grants.add(ref.artifact_id)
        return ref.artifact_id

    def read(self, resource_id: str) -> bytes:
        if resource_id not in self.grants:
            raise ValueError('media resource is not granted to this session')
        return self.store.read_bytes(resource_id)

