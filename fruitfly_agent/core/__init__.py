"""Stable FruitFlyAgent runtime and public extension contracts.

Concrete algorithms and Provider SDKs stay outside Core. See README.md for
public entry points, failure handling, cancellation, and module boundaries.
tests/contracts/test_public_api.py pins the exported API.
"""

from .config import AgentLoopConfig, ToolExecutionConfig
from .env import ExecutionEnv
from .errors import (
    FatalError,
    OverflowError,
    Result,
    RetryableError,
    SessionCorruptError,
    TaggedError,
    ValidationError,
)
from .extensions.hooks import HookRegistry
from .loop import run_agent_loop
from .extensions.protocols import Provider, SessionLike
from .context import (
    ContextFrame,
    ContextPhase,
    ContextPipeline,
    ContextPipelineProfile,
    ContextProvenance,
    ContextReducer,
    ContextStage,
    ContextTransform,
    ContextTransformer,
)
from .mechanisms import (
    ActivationScope,
    MechanismContribution,
    MechanismDescriptor,
    MechanismEffects,
    MechanismFamily,
    MechanismLayer,
    ParameterDescriptor,
    ParameterKind,
)
from .session import Session
from .tool_runtime import AgentTool, ToolCallContext
from .data_model.messages import (
    AgentLoopResult,
    AgentMessage,
    AgentToolResult,
    AssistantMessage,
    CustomMessage,
    ImageBlock,
    StopReason,
    TextBlock,
    ThinkingBlock,
    ToolCallBlock,
    ToolResultMessage,
    Usage,
    UserMessage,
)
from .data_model.context import ContextDecision, ContextItem, ContextSnapshot, ContextTrigger

__all__ = [
    "run_agent_loop",
    "AgentLoopConfig",
    "ToolExecutionConfig",
    "AgentTool",
    "ToolCallContext",
    "AgentToolResult",
    "AgentLoopResult",
    "AgentMessage",
    "AssistantMessage",
    "CustomMessage",
    "ImageBlock",
    "StopReason",
    "TextBlock",
    "ThinkingBlock",
    "ToolCallBlock",
    "ToolResultMessage",
    "Usage",
    "UserMessage",
    "HookRegistry",
    "ExecutionEnv",
    "Session",
    "Result",
    "TaggedError",
    "OverflowError",
    "RetryableError",
    "FatalError",
    "ValidationError",
    "SessionCorruptError",
    "Provider",
    "ContextReducer",
    "SessionLike",
    "ContextTrigger",
    "ContextItem",
    "ContextSnapshot",
    "ContextDecision",
    "ContextPipeline",
    "ContextPipelineProfile",
    "ContextPhase",
    "ContextFrame",
    "ContextProvenance",
    "ContextTransform",
    "ContextTransformer",
    "ContextStage",
    "ParameterKind",
    "ParameterDescriptor",
    "MechanismLayer",
    "MechanismFamily",
    "MechanismContribution",
    "MechanismEffects",
    "MechanismDescriptor",
    "ActivationScope",
]
