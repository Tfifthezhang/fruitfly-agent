"""Improvement orchestration outcomes and workflow contract."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Protocol
from fruitfly_agent.improvement.contracts.versions import canonical_json, content_hash
from fruitfly_agent.improvement.contracts.tasks import TaskMaterial
from fruitfly_agent.improvement.contracts.components import HarnessSnapshot
from fruitfly_agent.improvement.contracts.candidates import CandidateBundle
from fruitfly_agent.improvement.contracts.plans import RunPlan, ExperienceEntry
from fruitfly_agent.improvement.contracts.execution import ExecutionRecord
from fruitfly_agent.improvement.contracts.assessment import SelectionDecision
from fruitfly_agent.improvement.contracts.editing import JobServices
from fruitfly_agent.improvement.contracts.search import ExplorationDecision


@dataclass(frozen=True)
class ImprovementOutcome:
    plan: RunPlan
    task: TaskMaterial
    selected: ExecutionRecord | None
    harness: HarnessSnapshot
    candidates: tuple[CandidateBundle, ...]
    records: tuple[ExecutionRecord, ...]
    decision: SelectionDecision | None
    experience: tuple[ExperienceEntry, ...] = ()
    stop_reason: str = 'completed'
    verification: str = ''
    exploration: tuple[ExplorationDecision, ...] = ()


class WorkflowController(Protocol):
    async def run(self, plan: RunPlan, task: TaskMaterial, baseline: HarnessSnapshot,
                  services: JobServices, *, experience: tuple[ExperienceEntry, ...] = ()) -> ImprovementOutcome: ...


def experience_id(entries):
    return content_hash(canonical_json([asdict(e) for e in entries]))

__all__ = ["ImprovementOutcome", "WorkflowController", "experience_id"]
