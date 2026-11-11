"""Readable evidence views are independent of editing and quality judgments."""
from dataclasses import dataclass
from .tasks import Resource, TaskMaterial
from .execution import ExecutionRecord
from .versions import canonical_json, content_hash


@dataclass(frozen=True)
class OrganizationRequest:
    tasks: tuple[TaskMaterial, ...]
    records: tuple[ExecutionRecord, ...]
    instruction: str = 'Organize the supplied batch for reading.'
    context: tuple[Resource, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, 'tasks', tuple(self.tasks))
        object.__setattr__(self, 'records', tuple(self.records))
        object.__setattr__(self, 'context', tuple(self.context))
        tasks = {t.task_id: t for t in self.tasks}
        if len(tasks) != len(self.tasks) or not tasks:
            raise ValueError('organization requires distinct granted tasks')
        if len({r.run_id for r in self.records}) != len(self.records):
            raise ValueError('organization requires distinct execution identities')
        for record in self.records:
            if record.task_id not in tasks or record.material_id != tasks[record.task_id].material_id:
                raise ValueError('organization receipt is outside its task grant')


@dataclass(frozen=True)
class EvidenceView:
    resources: tuple[Resource, ...]
    source_ids: tuple[str, ...]
    implementation_id: str
    instructions_id: str

    @property
    def identity(self):
        from dataclasses import asdict
        return content_hash(canonical_json(asdict(self)))


@dataclass(frozen=True)
class OrganizationPart:
    """One retained child finding; reuse never certifies a new original read."""
    question: str
    context: str
    worker: str
    conditions: dict
    grant: dict
    findings: dict
    citations: dict
    producer: dict
    reusable: bool

    def __post_init__(self):
        from .validation import identifier, relative_path, bounded
        from .versions import require_hash
        from .evidence import EvidenceSpan
        bounded(self.question, 16000)
        bounded(self.context, 16000, empty=True)
        identifier(self.worker)
        if type(self.reusable) is not bool or not isinstance(self.conditions, dict):
            raise ValueError('invalid organization part conditions')
        if set(self.producer) != {'scope_id', 'agent_id', 'run_id'}:
            raise ValueError('organization part requires its original producer')
        for value in self.producer.values():
            identifier(value)
        if not isinstance(self.grant, dict) or not self.grant or not isinstance(self.citations, dict):
            raise ValueError('organization part requires original material identities')
        for path, reference in self.grant.items():
            relative_path(path); require_hash(reference)
        for citation, value in self.citations.items():
            if not isinstance(value, dict) or value.get('path') not in self.grant or value.get('artifact_id') != self.grant[value['path']]:
                raise ValueError('part citation is outside its immutable material grant')
            if value.get('kind') == 'text':
                if set(value) != {'path', 'artifact_id', 'kind', 'start', 'end'}:
                    raise ValueError('part text citations require exact source ranges')
                expected = EvidenceSpan(value['artifact_id'], value['start'], value['end']).citation_id
            elif value.get('kind') == 'image' and set(value) == {'path', 'artifact_id', 'kind'}:
                expected = value['artifact_id']
            else:
                raise ValueError('invalid part citation kind')
            if citation != expected:
                raise ValueError('organization part citation identity mismatch')
        if not isinstance(self.findings, dict) or set(self.findings) != {'summary', 'sources', 'unknowns'}:
            raise ValueError('organization part requires structured findings')
        bounded(self.findings['summary'], 24000)
        if (not isinstance(self.findings['unknowns'], list)
                or any(not isinstance(v, str) for v in self.findings['unknowns'])
                or not isinstance(self.findings['sources'], list)):
            raise ValueError('invalid organization part findings')
        for source in self.findings['sources']:
            if (not isinstance(source, dict) or set(source) != {'path', 'citation_id'}
                    or source['citation_id'] not in self.citations
                    or self.citations[source['citation_id']]['path'] != source['path']):
                raise ValueError('organization part cites an unretained source span')

    def to_dict(self):
        from dataclasses import asdict
        return asdict(self)

    @classmethod
    def from_dict(cls, value):
        from dataclasses import fields
        if not isinstance(value, dict) or set(value) != {f.name for f in fields(cls)}:
            raise ValueError('invalid organization part record')
        return cls(**value)
