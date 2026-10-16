"""Task material views and services, independent of improvement execution."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class TaskPackView:
    pack_id: str
    name: str
    source_hash: str
    train_count: int
    validation_count: int
    holdout_count: int
    writable: bool
    error: str = ""
    default_direction: str = ""
    acceptance_example: str = ""


@dataclass(frozen=True)
class CorrectionView:
    task_id: str
    input: str
    output: str
    context_warning: bool = False


@runtime_checkable
class TaskPackClient(Protocol):
    @property
    def task_packs_available(self) -> bool: ...
    def task_packs(self) -> tuple[TaskPackView, ...]: ...
    def correction_tasks(self) -> tuple[CorrectionView, ...]: ...
    def save_training_task(self, task_id: str, pack_id: str, input: str, expected: str, **options) -> TaskPackView: ...
    def task_pack_holdout(self, pack_id: str) -> tuple[tuple[str, str], ...]: ...


@runtime_checkable
class TaskPackService(Protocol):
    """Optional injected material capability, independent of search enablement."""
    def task_packs(self) -> tuple[TaskPackView, ...]: ...
    def save_training_task(self, pack_id: str, input: str, expected: str, **options) -> TaskPackView: ...
    def task_pack_holdout(self, pack_id: str) -> tuple[tuple[str, str], ...]: ...


