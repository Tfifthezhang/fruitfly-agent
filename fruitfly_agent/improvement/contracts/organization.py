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
