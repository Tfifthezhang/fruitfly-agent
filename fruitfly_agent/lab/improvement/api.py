"""Reviewed Lab composition and progress interfaces for hosts and extensions."""
from dataclasses import dataclass
from typing import Any, Callable, Protocol, runtime_checkable

from fruitfly_agent.improvement.contracts.execution import TaskRunner
from fruitfly_agent.improvement.contracts.assessment import Selector, MeasurementSource, VerificationPolicy
from fruitfly_agent.improvement.contracts.editing import Composer, Reflector, EditorSession, EvidenceInspector
from fruitfly_agent.improvement.contracts.pipeline import WorkflowController
from .components import ComponentRegistry, component_registry, bundle_target, bundle_text
from fruitfly_agent.lab.improvement.workflow import ImprovementWorkflow as ComponentWorkflow
from fruitfly_agent.lab.improvement.editor.generators import GeneratorRegistry, AgentGenerator, AgentComposer
from fruitfly_agent.lab.improvement.editor import AgentEditor, model_completion
from fruitfly_agent.lab.improvement.assessment.selection import AgentSelector
from fruitfly_agent.lab.improvement.experience.reflection import AgentReflector
from .assessment.inspection import ReadOnlyInspector
from fruitfly_agent.lab.improvement.termination.composition import policy_spec
from .assessment.completed import CompletedAssessmentService
from .evidence.indexing import organize_evidence
from .strategies.exploration import ExplorationSettings, ExplorationRegistry, builtin_explorations, validate_exploration
from .registration import SETTINGS, EDITOR_CONFIG, ASSESSOR_CONFIG, EDITOR_INSTRUCTIONS, SYSTEM_SETTINGS
from .system_configuration import exploration_settings
from .experience import entry_to_dict, entry_from_dict, experience_id
from .execution import ExecutionContext, ExecutionRegistry, builtin_executions
from .strategies import StrategyRegistry, builtin_strategies
from .workflow.mechanisms import install_workflow_mechanisms, extension_spec
from fruitfly_agent.improvement.contracts.stopping import StopPolicy
from fruitfly_agent.improvement.evidence.reporting import SearchReport, TokenUsage

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
    exploration: ExplorationSettings | None = None
    explorations: ExplorationRegistry | None = None
    component_options: dict | None = None
    hooks: Callable[[ExecutionContext], None] | None = None
    delivery_backend: Any = None
    workflow_settings: dict | None = None
    evidence_settings: dict | None = None

@dataclass(frozen=True)
class SearchActivity:
    """Progress counters; no invented percentage or token estimates."""
    phase: str
    completed: int = 0
    total: int = 0
    model_calls: int = 0
    trial_calls: int = 0
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

__all__ = [
    'ASSESSOR_CONFIG',
    'AgentComposer',
    'AgentEditor',
    'AgentGenerator',
    'AgentReflector',
    'AgentSelector',
    'CompletedAssessmentService', 'organize_evidence',
    'ComponentWorkflow',
    'EDITOR_CONFIG',
    'EDITOR_INSTRUCTIONS',
    'ExecutionContext',
    'ExplorationSettings',
    'GeneratorRegistry',
    'ReadOnlyInspector',
    'SETTINGS',
    'SYSTEM_SETTINGS',
    'SearchActivity',
    'SearchActivitySource',
    'SearchCompletion',
    'SearchCompletionSource',
    'WorkflowBindings',
    'builtin_executions',
    'builtin_explorations',
    'builtin_strategies',
    'bundle_target',
    'bundle_text',
    'component_registry',
    'entry_from_dict',
    'entry_to_dict',
    'experience_id',
    'extension_spec',
    'install_workflow_mechanisms',
    'model_completion',
    'policy_spec',
    'validate_exploration', 'evaluator_instructions', 'exploration_settings',
]


def evaluator_instructions(settings):
    from .assessment.instructions import EvaluatorInstructions
    return EvaluatorInstructions(**settings.get('evaluator', {}).get('instructions', {}))
