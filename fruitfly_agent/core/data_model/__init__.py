"""Unified public entry for FruitFlyAgent's core data contracts.

External callers may import from this package. Core internals import the leaf
modules directly so their dependency ownership remains explicit.
"""

from .messages import (
    CUSTOM_KIND_BRANCH,
    CUSTOM_KIND_COMPACTION,
    AgentLoopResult,
    AgentMessage,
    AgentToolResult,
    AssistantMessage,
    ContentBlock,
    CustomMessage,
    ImageBlock,
    StopReason,
    TextBlock,
    ThinkingBlock,
    ToolCallBlock,
    ToolResultMessage,
    Usage,
    UserMessage,
    block_from_dict,
    encode_image_bytes,
    message_from_dict,
)
from .context import ContextDecision, ContextItem, ContextSnapshot, ContextTrigger
from .runtime import (
    AgentLoopContext,
    BeforeToolCallResult,
    ProviderView,
)

__all__ = [
    "TextBlock",
    "ThinkingBlock",
    "ToolCallBlock",
    "ImageBlock",
    "ContentBlock",
    "block_from_dict",
    "StopReason",
    "Usage",
    "CUSTOM_KIND_COMPACTION",
    "CUSTOM_KIND_BRANCH",
    "UserMessage",
    "AssistantMessage",
    "ToolResultMessage",
    "CustomMessage",
    "AgentMessage",
    "message_from_dict",
    "AgentToolResult",
    "AgentLoopResult",
    "encode_image_bytes",
    "AgentLoopContext",
    "ProviderView",
    "BeforeToolCallResult",
    "ContextTrigger",
    "ContextItem",
    "ContextSnapshot",
    "ContextDecision",
]
