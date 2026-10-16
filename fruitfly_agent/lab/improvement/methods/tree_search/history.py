"""Immutable parent-linked discovery outcomes; no invented replay transitions."""
from dataclasses import dataclass, asdict
import json
import math
from pathlib import Path
from uuid import uuid4
from ...contracts.versions import canonical_json, content_hash
from ...tasks import safe_path


@dataclass(frozen=True)
class DiscoveryNode:
    node_id: str
    parent: str
    order: int
    text: str
    score: float | None
    status: str = 'scored'
    feedback: str = ''

    def __post_init__(self):
        if not isinstance(self.text, str) or len(self.text) > 30000 or not isinstance(self.feedback, str) or len(self.feedback) > 4000:
            raise ValueError('unbounded discovery content')
        if type(self.order) is not int or self.order < 0 or self.node_id != f'n{self.order}':
            raise ValueError('discovery node identity must match creation order')
        if self.status not in {'scored', 'error'}:
            raise ValueError('unknown discovery status')
        if self.status == 'scored':
            if isinstance(self.score, bool) or not isinstance(self.score, (int, float)) or not math.isfinite(self.score) or self.score < 0:
                raise ValueError('scored nodes need finite nonnegative scores')
        elif self.score is not None:
            raise ValueError('failed discovery attempts have no score')


@dataclass(frozen=True)
class DiscoveryWorld:
    conditions: str
    nodes: tuple[DiscoveryNode, ...]
    schema_version: int = 1

    def __post_init__(self):
        object.__setattr__(self, 'nodes', tuple(self.nodes))
        if type(self.schema_version) is not int or self.schema_version != 1 or not isinstance(self.conditions, str) or not self.conditions or not 1 <= len(self.nodes) <= 512:
            raise ValueError('invalid discovery world')
        seen, used = {'root'}, set()
        for order, node in enumerate(self.nodes):
            if node.order != order or node.parent not in seen or node.node_id in seen:
                raise ValueError('invalid discovery parent or order')
            if node.parent != 'root' and node.parent in used:
                raise ValueError('non-root discovery nodes have only one recorded child')
            seen.add(node.node_id)
            used.add(node.parent)

    def serialize(self):
        return canonical_json(asdict(self))

    @property
    def identity(self):
        return content_hash(self.serialize())

    @classmethod
    def parse(cls, text):
        value = json.loads(text)
        if not isinstance(value, dict) or set(value) != {'schema_version', 'conditions', 'nodes'}:
            raise ValueError('invalid discovery document')
        return cls(value['conditions'], tuple(DiscoveryNode(**n) for n in value['nodes']), value['schema_version'])


def load_worlds(workspace, path):
    root = safe_path(workspace, Path(path))
    files = sorted(root.glob('*.json')) if root.is_dir() else ([root] if root.is_file() else [])
    if not files or len(files) > 32:
        raise ValueError('need 1–32 completed discovery histories; run tree search first')
    worlds, sources = [], []
    for file in files:
        file = safe_path(workspace, file)
        if file.stat().st_size > 2_000_000:
            raise ValueError('discovery history exceeds 2 MB')
        text = file.read_text(encoding='utf-8')
        worlds.append(DiscoveryWorld.parse(text))
        sources.append((str(file), content_hash(text)))
    return tuple(worlds), tuple(sources)


def save_world(workspace, path, world):
    root = safe_path(workspace, Path(path))
    root.mkdir(parents=True, exist_ok=True)
    destination = safe_path(workspace, root / (uuid4().hex + '.json'))
    text = world.serialize()
    if len(text.encode('utf-8')) > 2_000_000:
        raise ValueError('discovery history exceeds 2 MB')
    with destination.open('x', encoding='utf-8') as stream:
        stream.write(text)
    return str(destination.relative_to(workspace))
