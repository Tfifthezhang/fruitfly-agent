"""Independent Improvement contracts and runtime; concrete algorithms are injected."""
from fruitfly_agent.improvement.contracts.tasks import TaskMaterial, Resource, ArtifactAccess
from fruitfly_agent.improvement.contracts.components import ComponentDocument, ComponentFile, HarnessSnapshot
from fruitfly_agent.improvement.contracts.candidates import CandidateBundle, EditReason
from fruitfly_agent.improvement.contracts.execution import ExecutionRecord, TaskRunner
from fruitfly_agent.improvement.contracts.assessment import Measurement, SelectionDecision, Selector, MeasurementSource, VerificationPolicy
from fruitfly_agent.improvement.contracts.plans import RunPlan, ExperienceEntry
from fruitfly_agent.improvement.contracts.editing import ProposalRequest, ProposalResult, CompositionRequest, CandidateGenerator, GenerationServices, Composer, Reflector
from fruitfly_agent.improvement.contracts.pipeline import ImprovementOutcome, WorkflowController
from .contracts.facts import ExecutionFacts, UsageFact, ArtifactFact
from .contracts.evaluation import EvaluationBatch, TrialResult, CandidateEvaluation
from .contracts.experiments import EpisodeExecutor, EpisodeRequest, EpisodeResult
from .workflow.controller import ImprovementWorkflow
from .workflow.engine import SearchEngine
from .workflow.problems import SearchProblem
from .workflow.services import WorkflowServices, GeneratorServices
from .execution.scheduler import TaskScheduler
from .execution.handles import ManagedExecution, CompletionOnlyRunner
from .execution.facts import attach_facts, ensure_facts, read_facts, receipt_facts
from .components.registry import ComponentRegistry

from .contracts.failures import Failure, StageFailure, IntegrityError, PersistenceError, CleanupError

from .contracts.lifecycle import LifecycleEvent, ContextContribution
from .extensions.hooks import HookRegistry

from fruitfly_agent.core.extensions.operations import OperationSupervisor

from .contracts.optimization import OptimizationSpec, OptimizationAdapter, TextProjection
