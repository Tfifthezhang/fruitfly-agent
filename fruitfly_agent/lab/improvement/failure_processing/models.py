"""Learning material is derived from scored training observations, not holdout answers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from fruitfly_agent.lab.improvement.contracts.search import TaskCase, TrialObservation, content_id


@dataclass(frozen=True)
class FailureExample:
    case: TaskCase
    observation: TrialObservation
    material: str = ""

    def __post_init__(self):
        if (self.observation.case_id != self.case.case_id
                or self.observation.partition != "train"
                or self.observation.status != "ok"
                or self.observation.score is None):
            raise ValueError("failure material requires a scored, matching training observation")
        if not isinstance(self.material, str) or len(self.material) > 60000:
            raise ValueError("failure evidence projection must be bounded immutable text")


@dataclass(frozen=True)
class LearningTask:
    case: TaskCase
    source_case_id: str
    method_id: str
    review: str
    policy_id: str = ""
    execution_id: str = ""

    def __post_init__(self):
        if not all(isinstance(v, str) and v.strip() for v in
                   (self.source_case_id, self.method_id, self.review)):
            raise ValueError("learning tasks require source, method and review identities")
        if not isinstance(self.policy_id, str) or not isinstance(self.execution_id, str):
            raise ValueError("learning policy identities must be text")

    @property
    def task_id(self):
        return content_id(self.source_case_id + "\0" + self.case.case_id + "\0" + self.method_id + "\0" + self.policy_id)


@dataclass(frozen=True)
class LearningMaterial:
    tasks: tuple[LearningTask, ...]
    method_id: str

    def __post_init__(self):
        object.__setattr__(self, "tasks", tuple(self.tasks))
        if not self.method_id or not 1 <= len(self.tasks) <= 12:
            raise ValueError("learning material needs a method and 1–12 tasks")
        if len({task.case.case_id for task in self.tasks}) != len(self.tasks):
            raise ValueError("duplicate learning tasks")
        if any(task.method_id != self.method_id for task in self.tasks):
            raise ValueError("learning task method differs from its material")


class ProcessingServices(Protocol):
    def check(self) -> None: ...
    def record(self, kind: str, **fields: object) -> str: ...
    async def complete(self, role: str, system: str, prompt: str) -> str: ...


class FailureProcessor(Protocol):
    implementation_id: str
    async def process(self, failures: tuple[FailureExample, ...], services: ProcessingServices,
                      *, policy, limit: int) -> LearningMaterial: ...
