"""Improvement orchestration values and compatible explicit contract exports."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Protocol
from fruitfly_agent.improvement.contracts.validation import identifier, relative_path, bounded
from fruitfly_agent.improvement.contracts.versions import SystemVersion, canonical_json, content_hash, require_hash
from fruitfly_agent.improvement.contracts.tasks import Resource, TaskMaterial, ArtifactAccess, TaskSource
from fruitfly_agent.improvement.contracts.components import ComponentFile, ComponentDocument, HarnessSnapshot, ComponentAdapter
from fruitfly_agent.improvement.contracts.candidates import EditReason, CandidateBundle
from fruitfly_agent.improvement.contracts.plans import RunPlan, ExperienceEntry
from fruitfly_agent.improvement.contracts.execution import ExecutionRecord, TaskRunner
from fruitfly_agent.improvement.contracts.assessment import Measurement, SelectionDecision, Selector, MeasurementSource, VerificationPolicy
from fruitfly_agent.improvement.contracts.editing import (ProposalRequest, ProposalResult, CompositionRequest, GenerationServices, JobServices,
    JobResource, EditorWorkspace, InspectionInstructions, EvidenceInspector, CandidateGenerator,
    GeneratorDefinition, Composer, Reflector, ExperienceRepository, EditorSession)
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

