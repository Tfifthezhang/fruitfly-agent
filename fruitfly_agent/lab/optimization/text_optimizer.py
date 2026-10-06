"""Text search values: algorithms do not own persistence or adoption."""
from dataclasses import dataclass
from typing import Protocol, runtime_checkable
import math
import re
from fruitfly_agent.lab.algorithms.targets import validate_text
from .reporting import SearchReport, TokenUsage, restore_search_report

TEXT_OPTIMIZER_COMPONENT = 'text-optimizer'
TEXT_OPTIMIZATION_TARGET_COMPONENT = 'optimization-target-id'


@dataclass(frozen=True)
class SearchPreview:
    algorithm: str
    label: str
    cost_notice: str
    details: tuple[tuple[str, str], ...] = ()
    target_id: str = "base_prompt"
    preview_token: str = ""

    def __post_init__(self):
        if not all(isinstance(v, str) and v.strip() for v in (self.algorithm, self.label, self.cost_notice, self.target_id)):
            raise ValueError("preview must declare algorithm, label, cost notice and target")
        if any(len(pair) != 2 or not all(isinstance(v, str) for v in pair) for pair in self.details):
            raise ValueError("preview details must be text label/value pairs")
        object.__setattr__(self, 'details', tuple(tuple(pair) for pair in self.details))


@dataclass(frozen=True)
class TextProposal:
    text: str
    algorithm: str
    cases_digest: str = ''
    seed_score: float | None = None
    validation_score: float | None = None
    metric_calls: int = 0
    evidence: tuple[tuple[str, str], ...] = ()
    report: SearchReport | None = None

    def __post_init__(self):
        validate_text(self.text)
        if self.report is not None and not isinstance(self.report, SearchReport):
            raise ValueError('proposal report must be a SearchReport')
        if not isinstance(self.algorithm, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', self.algorithm):
            raise ValueError('invalid proposal algorithm identity')
        if isinstance(self.metric_calls, bool) or not isinstance(self.metric_calls, int) or self.metric_calls < 0:
            raise ValueError('metric calls must be non-negative')
        for value in (self.seed_score, self.validation_score):
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)):
                raise ValueError('optional search scores must be finite numbers')
        if any(len(pair) != 2 or not all(isinstance(v, str) for v in pair) for pair in self.evidence):
            raise ValueError('proposal evidence must be text label/value pairs')
        object.__setattr__(self, 'evidence', tuple(tuple(pair) for pair in self.evidence))


@runtime_checkable
class TextOptimizer(Protocol):
    """Deliver complete proposals in preferred order; the host publishes the first."""
    def preview(self, *, task=None) -> SearchPreview: ...
    async def search(self, prompt: str, direction: str, *, parent_manifest: str, task=None) -> tuple[TextProposal, ...]: ...
    def cancel(self) -> bool: ...


@dataclass(frozen=True)
class SearchActivity:
    """Presentation snapshot; counters are usage, never whole-search completion."""
    phase: str
    completed: int = 0
    total: int = 0
    model_calls: int = 0
    model_limit: int = 0
    trial_calls: int = 0
    trial_limit: int = 0
    failed_trials: int = 0
    tokens: TokenUsage = TokenUsage()


@runtime_checkable
class SearchActivitySource(Protocol):
    """Optional read-only progress capability, independent of search strategies."""
    def progress(self) -> SearchActivity | None: ...
