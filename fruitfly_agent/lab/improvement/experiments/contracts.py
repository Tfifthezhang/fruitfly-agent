"""Optional original-task host contracts, independent of generic role requests."""
from dataclasses import dataclass
from typing import Any, Callable, Protocol
from ..contracts.versions import SystemVersion
from .models import ExperimentTasks

@dataclass(frozen=True)
class BenchmarkContext:
    tasks: ExperimentTasks
    parent: SystemVersion
    parent_manifest: str
    baseline: str
    direction: str
    executor: Any
    packet_for_text: Callable[[str], dict]
    read_artifact: Callable[[str], str]
    original_evidence_id: str = ""


class ExperimentImprover(Protocol):
    def experiment_available(self) -> bool: ...
    def experiment_target_id(self) -> str: ...
    def experiment_timeout_seconds(self) -> int: ...
    def preview_experiment_plan(self, task_count: int): ...
    def improvement_identity(self) -> dict: ...
    def preview_experiment(self, context: BenchmarkContext): ...
    async def search_experiment(self, context: BenchmarkContext): ...
