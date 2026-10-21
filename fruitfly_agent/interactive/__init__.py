"""Renderer-neutral interaction boundary and the built-in terminal frontend."""

from fruitfly_agent.interactive.contracts.improvement import ImprovementPreview, ImprovementService
from fruitfly_agent.interactive.contracts.candidates import (
    CandidateView,
    CandidateSection,
    CandidateService,
    CandidateClient,
    CandidateActivationService,
    CandidateActivationClient,
)
from fruitfly_agent.interactive.contracts.task_packs import (
    TaskPackView,
    CorrectionView,
    TaskPackClient,
    TaskPackService,
)

from fruitfly_agent.interactive.application import (
    AgentApplication,
    ApplicationState,
    RuntimeFactory,
    RuntimeHandle,
)
from fruitfly_agent.interactive.contracts.configuration import (
    ConfigurationActionResult,
    ConfigurationController,
    ConfigurationLaunchResult,
    ConfigurationMechanism,
    ConfigurationSelectionGroup,
    ConfigurationParameter,
    ConfigurationSnapshot,
)
from fruitfly_agent.interactive.contracts.events import (
    AssistantTextDelta,
    AssistantThinkingDelta,
    CompactionStarted,
    FrontendEvent,
    InteractiveEvent,
    RunActivityChanged,
    RunFinished,
    RunStarted,
    ToolFinished,
    ToolOutput,
    ToolStarted,
    event_from_dict,
)

from fruitfly_agent.interactive.contracts.events import EventSink
from fruitfly_agent.interactive.contracts.models import (
    ConversationBlock,
    ConversationMessage,
    InteractiveMechanism,
    InteractiveStatus,
    ResumableSession,
)
from fruitfly_agent.interactive.session import InteractiveSession
from fruitfly_agent.interactive.contracts.runtime import RuntimeSession
from fruitfly_agent.interactive.terminal import (
    LineEditor,
    TerminalConfigurationFrontend,
    TerminalImprovementFrontend,
    TerminalFrontend,
    TerminalRenderer,
    TerminalResumeFrontend,
)

__all__ = [
    "ConversationBlock",
    "ConversationMessage",
    "TaskPackView",
    "CorrectionView",
    "TaskPackClient",
    "TaskPackService",
    "ImprovementPreview",
    "CandidateView",
    "CandidateSection",
    "CandidateService",
    "CandidateClient",
    "ImprovementService",
    "CandidateActivationService",
    "CandidateActivationClient",
    "AgentApplication",
    "ApplicationState",
    "RuntimeFactory",
    "RuntimeHandle",
    "RuntimeSession",
    "ConfigurationParameter",
    "ConfigurationMechanism",
    "ConfigurationSelectionGroup",
    "ConfigurationSnapshot",
    "ConfigurationActionResult",
    "ConfigurationLaunchResult",
    "ConfigurationController",
    "FrontendEvent",
    "InteractiveEvent",
    "event_from_dict",
    "RunStarted",
    "RunActivityChanged",
    "AssistantTextDelta",
    "AssistantThinkingDelta",
    "ToolStarted",
    "ToolOutput",
    "ToolFinished",
    "CompactionStarted",
    "RunFinished",
    "EventSink",
    "LineEditor",
    "InteractiveSession",
    "InteractiveMechanism",
    "InteractiveStatus",
    "ResumableSession",
    "TerminalFrontend",
    "TerminalConfigurationFrontend",
    "TerminalImprovementFrontend",
    "TerminalRenderer",
    "TerminalResumeFrontend",
]
