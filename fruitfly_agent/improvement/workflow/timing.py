"""Independent invocation deadlines; usage observations never authorize work."""
from contextvars import ContextVar
from dataclasses import dataclass
import time


@dataclass(frozen=True)
class StageClock:
    owner: object
    stage: str
    started: float
    deadline: float

    def check(self):
        if time.monotonic() >= self.deadline:
            raise TimeoutError(self.stage + ' timed out')


current_stage: ContextVar[StageClock | None] = ContextVar('improvement_stage', default=None)


def stage_role(stage):
    if stage in {'execute', 'execution'}:
        return 'execution'
    if stage in {'propose', 'compose', 'reflect', 'editor'}:
        return 'editor'
    return 'evaluator'
