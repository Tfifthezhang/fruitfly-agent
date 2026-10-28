"""Task output manifests, distinct from executable harness configuration bundles."""
from dataclasses import dataclass
import json

from fruitfly_agent.improvement.contracts.tasks import Resource
from fruitfly_agent.improvement.contracts.validation import relative_path
from fruitfly_agent.improvement.contracts.versions import canonical_json, content_hash


@dataclass(frozen=True)
class DeliverySpec:
    entrypoint: str
    dependencies: tuple[str, ...] = ()
    inputs: tuple[str, ...] = ()
    arguments: tuple[str, ...] = ()
    timeout_seconds: int = 30
    require_stdout: bool = True

    def __post_init__(self):
        for name in ('dependencies', 'inputs', 'arguments'):
            if not isinstance(getattr(self, name), (list, tuple)):
                raise ValueError('delivery fields require explicit lists')
            object.__setattr__(self, name, tuple(getattr(self, name)))
        paths = (self.entrypoint, *self.dependencies, *self.inputs)
        for path in paths:
            relative_path(path)
        if len(set(paths)) != len(paths) or len(paths) > 256:
            raise ValueError('delivery paths must be distinct and bounded')
        if (type(self.timeout_seconds) is not int or not 1 <= self.timeout_seconds <= 600
                or type(self.require_stdout) is not bool or len(self.arguments) > 64
                or any(not isinstance(v, str) or len(v) > 4000 for v in self.arguments)):
            raise ValueError('invalid delivery execution parameters')

    @classmethod
    def parse(cls, data):
        if len(data) > 16000:
            raise ValueError('delivery manifest exceeds 16000 bytes')
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError('duplicate delivery manifest key')
                result[key] = value
            return result
        value = json.loads(data, object_pairs_hook=unique)
        if not isinstance(value, dict) or 'entrypoint' not in value or set(value) - set(cls.__dataclass_fields__):
            raise ValueError('unknown delivery manifest fields')
        for name in ('dependencies', 'inputs', 'arguments'):
            if name in value and not isinstance(value[name], list):
                raise ValueError('delivery lists must be JSON arrays')
        return cls(**value)


@dataclass(frozen=True)
class DeliveryBundle:
    run_id: str
    spec: DeliverySpec
    files: tuple[Resource, ...]

    @classmethod
    def collect(cls, record, task, spec):
        outputs = {r.path.removeprefix('deliverables/'): r for r in record.artifacts
                   if r.kind == 'deliverable' and r.path.startswith('deliverables/')}
        inputs = {r.path: r for r in task.inputs}
        files = []
        for name in (spec.entrypoint, *spec.dependencies, *spec.inputs):
            source = inputs if name in spec.inputs else outputs
            if name not in source:
                raise ValueError('declared delivery file is missing: ' + name)
            ref = source[name]
            files.append(Resource(name, ref.artifact_id, ref.media_type, ref.kind))
        return cls(record.run_id, spec, tuple(files))

    @property
    def bundle_id(self):
        from dataclasses import asdict
        return content_hash(canonical_json(asdict(self)))
