"""Independent Improvement contracts and runtime; concrete algorithms are injected."""
from .contracts.pipeline import (
    TaskMaterial, Resource, ComponentDocument, ComponentFile, HarnessSnapshot,
    CandidateBundle, EditReason, ExecutionRecord, Measurement, RunPlan,
    ProposalRequest, ProposalResult, CompositionRequest, SelectionDecision,
    ExperienceEntry, ImprovementOutcome, ArtifactAccess, ComponentAdapter,
    CandidateGenerator, GenerationServices, Composer, TaskRunner, Selector,
    Reflector, MeasurementSource, VerificationPolicy, WorkflowController,
)
from .contracts.facts import ExecutionFacts, BudgetFact, ArtifactFact
from .contracts.evaluation import EvaluationBatch, TrialResult, CandidateEvaluation
from .contracts.experiments import EpisodeExecutor, EpisodeRequest, EpisodeResult
from .workflow.controller import ImprovementWorkflow
from .workflow.engine import SearchEngine
from .workflow.problems import SearchProblem
from .workflow.services import WorkflowServices, GeneratorServices
from .workflow.budget import BudgetScope, AllocationExhausted
from .execution.scheduler import TaskScheduler
from .execution.handles import ManagedExecution, CompletionOnlyRunner
from .execution.facts import attach_facts, ensure_facts, read_facts, receipt_facts
from .components.registry import ComponentRegistry

from .contracts.failures import Failure, StageFailure, IntegrityError, PersistenceError, CleanupError

from .contracts.lifecycle import LifecycleEvent, ContextContribution
from .extensions.hooks import HookRegistry
