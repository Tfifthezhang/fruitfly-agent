"""Search contracts. Strategies own their loop; services never grant adoption."""
from __future__ import annotations

from dataclasses import dataclass, field
import asyncio
import hashlib
import math
from threading import Event
from typing import Literal, Protocol

from fruitfly_agent.lab.algorithms import AlgorithmSpec
from fruitfly_agent.lab.algorithms.targets import TargetSnapshot, validate_text


def content_id(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TaskCase:
    input: str
    expected: str
    verification: str = ""

    def __post_init__(self):
        if not isinstance(self.input, str) or not isinstance(self.expected, str):
            raise ValueError("case fields must be strings")
        if not self.input.strip() or not self.expected.strip():
            raise ValueError("case input and expected must not be empty")
        if not isinstance(self.verification, str) or len(self.verification) > 16000:
            raise ValueError("verification must be bounded immutable text")
        if len(self.input) > 4000 or len(self.expected) > 1000:
            raise ValueError("case exceeds the text size limit")

    @property
    def case_id(self):
        return content_id(self.input + "\0" + self.expected + ("\0" + self.verification if self.verification else ""))


@dataclass(frozen=True)
class ObjectivePolicy:
    policy_id: str = "normalized-exact-v1"
    metric: str = "accuracy"
    direction: Literal["max", "min"] = "max"

    def __post_init__(self):
        if not self.policy_id or not self.metric or self.direction not in ("max", "min"):
            raise ValueError("invalid objective policy")

    def utility(self, score: float) -> float:
        if not math.isfinite(score):
            raise ValueError("metric must be finite")
        return score if self.direction == "max" else -score

    def better(self, score: float, incumbent: float) -> bool:
        return self.utility(score) > self.utility(incumbent)


@dataclass(frozen=True)
class OptimizationProblem:
    search_id: str
    parent_manifest: str
    baseline: TargetSnapshot
    direction: str
    train: tuple[TaskCase, ...]
    validation: tuple[TaskCase, ...]
    cases_digest: str
    execution_id: str
    policy: ObjectivePolicy = field(default_factory=ObjectivePolicy)
    parameters: tuple[tuple[str, object], ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "train", tuple(self.train))
        object.__setattr__(self, "validation", tuple(self.validation))
        object.__setattr__(self, "parameters", tuple(tuple(pair) for pair in self.parameters))
        if any(not isinstance(value, (str, int, float, bool, type(None))) for _, value in self.parameters):
            raise ValueError("problem parameters must be immutable scalar values")
        if self.baseline.schema != "text-v1":
            raise ValueError("only text-v1 is supported")
        if not self.search_id or not self.parent_manifest or not self.execution_id:
            raise ValueError("search, parent and execution identities are required")
        if not self.direction.strip() or len(self.direction) > 500:
            raise ValueError("direction must contain 1–500 characters")
        if not self.train or not self.validation:
            raise ValueError("train and selection validation are required")
        if {c.input for c in self.train} & {c.input for c in self.validation}:
            raise ValueError("train and validation inputs must not overlap")


@dataclass(frozen=True)
class TrialObservation:
    evaluation_id: str
    candidate_id: str
    case_id: str
    partition: Literal["train", "validation"]
    execution_id: str
    policy_id: str
    status: Literal["ok", "error", "cancelled"]
    score: float | None
    output: str = ""
    feedback: str = ""

    def __post_init__(self):
        if self.status not in ("ok", "error", "cancelled"):
            raise ValueError("invalid trial status")
        if self.partition not in ("train", "validation"):
            raise ValueError("invalid partition")
        if self.status == "ok":
            if self.score is None or isinstance(self.score, bool) or not math.isfinite(self.score):
                raise ValueError("successful trial requires a finite score")
        elif self.score is not None:
            raise ValueError("failed trial must not carry a score")


@dataclass(frozen=True)
class Evaluation:
    text: str
    observations: tuple[TrialObservation, ...]
    score: float | None


@dataclass(frozen=True)
class SearchCandidate:
    text: str
    score: float
    evidence: tuple[tuple[str, str], ...] = ()

    def __post_init__(self):
        validate_text(self.text)
        if isinstance(self.score, bool) or not math.isfinite(self.score):
            raise ValueError("candidate score must be finite")
        if any(len(pair) != 2 or not all(isinstance(v, str) for v in pair) for pair in self.evidence):
            raise ValueError("candidate evidence must contain text label/value pairs")
        object.__setattr__(self, "evidence", tuple(tuple(pair) for pair in self.evidence))


@dataclass(frozen=True)
class SearchResult:
    candidates: tuple[SearchCandidate, ...]
    seed_score: float | None
    stop_reason: str = "completed"

    def __post_init__(self):
        object.__setattr__(self, "candidates", tuple(self.candidates))
        if len(self.candidates) > 3 or len({c.text for c in self.candidates}) != len(self.candidates):
            raise ValueError("deliver at most three distinct candidates")
        if self.seed_score is not None and (isinstance(self.seed_score, bool) or not math.isfinite(self.seed_score)):
            raise ValueError("seed score must be finite or absent")


class SearchServices(Protocol):
    """Injected capabilities; implementations may evaluate without any model."""
    problem: OptimizationProblem
    stop: Event
    signal: asyncio.Event

    def check(self) -> None: ...
    def validate(self, text: str) -> None: ...
    def record(self, kind: str, **fields: object) -> str: ...
    def history(self) -> tuple[dict, ...]: ...
    async def evaluate(self, text: str, partition: str, *, cases=None) -> Evaluation: ...
    async def complete(self, role: str, system: str, prompt: str) -> str: ...
    async def agent(self, role: str, system: str, prompt: str, *, files: dict[str, str], output_path: str) -> str: ...


class Optimizer(Protocol):
    spec: AlgorithmSpec
    supported_schemas: frozenset[str]
    required_capabilities: frozenset[str]

    async def search(self, problem: OptimizationProblem, services: SearchServices) -> SearchResult: ...
