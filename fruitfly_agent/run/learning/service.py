"""Persist attributed material without granting search or activation authority."""
from dataclasses import asdict
import json
import os
from pathlib import Path
import tempfile

from fruitfly_agent.lab.catalog import build_learning
from fruitfly_agent.lab.algorithms.targets import content_hash


class RunLearningService:
    def __init__(self, workspace, policy, *, processor=None):
        self.root = Path(workspace) / '.fruitfly' / 'learning' / 'materials'
        self.workspace = Path(workspace).resolve()
        self.engine = build_learning(policy, processor=processor, save=self.save)

    async def observe(self, task):
        return await self.engine.observe(asdict(task))

    async def save(self, observation, material):
        self.root.resolve().relative_to(self.workspace)
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / (content_hash(observation.source_id).split(':')[1] + '.json')
        if path.is_symlink():
            raise ValueError('learning record must not be a symlink')
        payload = {'schema_version': 1, 'source': asdict(observation), 'material': asdict(material),
                   'partition': 'train', 'method': type(self.engine.processor).__name__}
        if path.exists():
            if json.loads(path.read_text()) == payload:
                return
            raise ValueError('learning source already has different material')
        fd, temporary = tempfile.mkstemp(prefix='.material-', dir=self.root)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)

    async def close(self):
        await self.engine.close()
