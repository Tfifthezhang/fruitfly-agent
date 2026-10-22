"""Public component-improvement ports consumed by hosts and external extensions."""
from dataclasses import dataclass
from typing import Any, Callable, Protocol, runtime_checkable

from .contracts.pipeline import (
    TaskMaterial, Resource, ComponentDocument, ComponentFile, HarnessSnapshot,
    CandidateBundle, EditReason, ExecutionRecord, Measurement, RunPlan,
    ProposalRequest, ProposalResult, CompositionRequest, SelectionDecision,
    ExperienceEntry, ImprovementOutcome, ArtifactAccess, ComponentAdapter,
    CandidateGenerator, GeneratorDefinition, GenerationServices, Composer, TaskRunner, Selector,
    Reflector, MeasurementSource, ExperienceRepository, VerificationPolicy,
    EditorSession, EvidenceInspector, EditorWorkspace, JobServices, JobResource, WorkflowController, TaskSource,
)
from .components import (ComponentRegistry, TextComponentAdapter, FileComponentAdapter,
    component_registry, bundle_target, bundle_text)
from .workflow import (ImprovementWorkflow as ComponentWorkflow, WorkflowServices,
    GeneratorRegistry, AgentGenerator, AgentComposer, AllocationExhausted)
from .workflow.execution import FileTaskRunner
from .editor import AgentEditor, AgentSelector, AgentReflector, model_completion
from .editor.instructions import EditorInstructions, EditorInstructionTarget
from .registration import SETTINGS, EDITOR_CONFIG, EDITOR_INSTRUCTIONS
from .materials import WorkspaceTaskSource
from .experience import entry_to_dict, entry_from_dict, experience_id
from .verification import CaseMeasurements, HoldoutVerification
from .contracts.experiments import (ExperimentSpec, EpisodeRequest, EpisodeResult, EpisodeExecutor,
    TrialReport, ExecutionRequest, ExecutionParameter, MaterialOption, PreparedExecution, ExecutionPorts, ExecutionDefinition)
from .execution import ExecutionContext, ExecutionRegistry, builtin_executions
from .workflow.budget import BudgetScope
from .workflow.stopping import StopPolicy, SearchState, BoundedStopPolicy
from .evidence.receipts import TaskReference, TaskRunEvidence, EvidenceArtifact
from .evidence.reporting import SearchReport, TokenUsage, restore_search_report


@dataclass(frozen=True)
class WorkflowBindings:
    """Replace stage implementations with factories owning one job's state."""
    generators: GeneratorRegistry | None = None
    runner: Callable[..., TaskRunner] | None = None
    composer: Callable[..., Composer] | None = None
    selector: Callable[..., Selector] | None = None
    reflector: Callable[..., Reflector] | None = None
    verifier: VerificationPolicy | None = None
    measurements: MeasurementSource | None = None
    workflow_factory: Callable[..., WorkflowController] | None = None
    editor: Callable[..., EditorSession] | None = None
    inspector: Callable[..., EvidenceInspector] | None = None
    components: Callable[..., ComponentRegistry] | None = None
    executions: ExecutionRegistry | None = None
    stop_policy: StopPolicy | None = None


@dataclass(frozen=True)
class SearchActivity:
    """Progress counters; no invented percentage or token estimates."""
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
    def progress(self) -> SearchActivity | None: ...


@dataclass(frozen=True)
class SearchCompletion:
    """Final results including unscored work; existing report records stay readable."""
    report: SearchReport
    evidence: tuple[tuple[str, str], ...] = ()
    summary: str = ''
    output: str = ''
    assurance: str = ''


@runtime_checkable
class SearchCompletionSource(Protocol):
    def completion(self) -> SearchCompletion | None: ...
