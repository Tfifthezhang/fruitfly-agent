"""Public component-improvement ports consumed by hosts and external extensions."""
from dataclasses import dataclass
from typing import Any, Callable, Protocol, runtime_checkable

from fruitfly_agent.improvement.contracts.pipeline import (
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
from .execution.file_runner import FileTaskRunner
from .editor import AgentEditor, AgentSelector, AgentReflector, model_completion
from .assessment.inspection import ReadOnlyInspector
from .assessment.online import AssessedRunner
from .assessment.metrics import ProcessMetrics
from .assessment.comparison import Objective, LexicographicComparison
from fruitfly_agent.improvement.contracts.live import (EvidencePosition, ExecutionEvent, Metric, Assessment,
    ExecutionHandle, OnlineAssessor, ExecutionControlPolicy, ControlRequest, ControlReceipt)
from fruitfly_agent.improvement.execution.handles import ManagedExecution, CompletionOnlyRunner
from fruitfly_agent.lab.improvement.termination import StopDecision, AnyOf, AllOf, StopRegistry, IterationLimit, NoImprovement, FailureLimit, ResourceLimit, ScoreAtLeast, MetricThreshold
from fruitfly_agent.lab.improvement.termination.composition import policy_spec
from .workflow.adaptive import StopExecutionPolicy
from fruitfly_agent.improvement.contracts.components import ComponentBinding, CandidateBuilder, CandidateRuntime, ActivationHost
from fruitfly_agent.improvement.contracts.versions import content_hash
from fruitfly_agent.improvement.contracts.validation import relative_path
from fruitfly_agent.improvement.contracts.facts import ExecutionFacts, BudgetFact, ArtifactFact
from fruitfly_agent.improvement.execution.facts import attach_facts, read_facts, receipt_facts, ensure_facts, loop_fact_values
from .components.changes import FileChange, ChangeSet
from fruitfly_agent.improvement.execution.segments import ExecutionSegment
from .assessment.registry import AssessorRegistry
from .assessment.registry import CompletedAssessorRegistry, CompletedAssessorDefinition, builtin_completed_assessors
from .assessment.configuration import ProcessAssessmentSettings
from .assessment.completed import CompletedAssessmentService
from fruitfly_agent.improvement.contracts.assessment import AssessmentUnavailable
from fruitfly_agent.improvement.contracts.search import ExplorationDecision
from fruitfly_agent.improvement.contracts.task_sets import (TaskEntry, TaskSetSnapshot, ScoreSpec, CollectionBinding, TaskSetSourceDefinition)
from fruitfly_agent.improvement.contracts.evaluation import (EvaluationBatch, TrialResult, CandidateEvaluation, JointAssessment,
    CandidateComparison, JointSelection, TaskSetOutcome)
from fruitfly_agent.improvement.contracts.editing import TaskSetProposalRequest, TaskSetCandidateGenerator
from fruitfly_agent.improvement.contracts.plans import TaskSetRunPlan
from .task_sets import TaskSetSourceRegistry, MultiTaskSettings, sample_batch
from .task_sets.execution import execution_definition as task_set_execution
from .task_sets.execution import minimum_budget as task_set_minimum_budget
from fruitfly_agent.improvement.execution.scheduler import TaskScheduler
from fruitfly_agent.improvement.execution.batches import BatchEvaluator
from .strategies.exploration import (ExplorationSettings, ExplorationRegistry, ExplorationDefinition,
    builtin_explorations, validate_process_configuration)
from .assessment.scorers.model import ModelAssessor
from .assessment.aggregation import WeightedSum
from .assessment.feedback import FeedbackProjection
from .editor.instructions import EditorInstructions, EditorInstructionTarget
from .registration import SETTINGS, EDITOR_CONFIG, ASSESSOR_CONFIG, EDITOR_INSTRUCTIONS, SYSTEM_SETTINGS
from .system_configuration import process_configuration, process_settings_values
from .materials import WorkspaceTaskSource
from .experience import entry_to_dict, entry_from_dict, experience_id
from .assessment.verification import CaseMeasurements, HoldoutVerification
from fruitfly_agent.improvement.contracts.experiments import (ExperimentSpec, EpisodeRequest, EpisodeResult, EpisodeExecutor,
    TrialReport, ExecutionRequest, ExecutionParameter, MaterialOption, PreparedExecution, ExecutionPorts, ExecutionDefinition)
from .execution.deliverables import DeliverySpec, DeliveryBundle
from .verification.delivery import DeliveryResult, CommandDeliveryBackend, DeliveryValidationRunner
from .execution import ExecutionContext, ExecutionRegistry, builtin_executions
from fruitfly_agent.improvement.workflow.budget import BudgetScope
from .strategies import StrategyRegistry, StrategyDefinition, SearchSchedule, builtin_strategies
from .workflow.mechanisms import install_workflow_mechanisms, extension_spec
from fruitfly_agent.improvement.extensions import HookRegistry
from fruitfly_agent.improvement.contracts.lifecycle import LifecycleEvent, ContextContribution
from .workflow.stopping import StopPolicy, SearchState, BoundedStopPolicy
from fruitfly_agent.improvement.evidence.receipts import TaskReference, TaskRunEvidence, EvidenceArtifact
from fruitfly_agent.improvement.evidence.reporting import SearchReport, TokenUsage, restore_search_report


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
    strategies: StrategyRegistry | None = None
    process_assessment: ProcessAssessmentSettings | None = None
    exploration: ExplorationSettings | None = None
    completed_assessors: CompletedAssessorRegistry | None = None
    explorations: ExplorationRegistry | None = None
    component_options: dict | None = None
    hooks: Callable[[ExecutionContext], None] | None = None
    delivery_backend: Any = None


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
