"""Programmatic-context externalization for ContextPipeline."""

from __future__ import annotations

from dataclasses import replace

from fruitfly_agent.core.data_model.messages import (
    AgentMessage,
    AssistantMessage,
    TextBlock,
    ToolResultMessage,
    UserMessage,
)
from fruitfly_agent.core.context import ContextFrame, ContextTransform

from .protocols import ContextArtifactWriter


class ProgrammaticContextExternalizer:
    """Externalize large projected messages without changing canonical facts."""

    def __init__(
        self,
        store: ContextArtifactWriter,
        *,
        threshold_chars: int,
        preview_chars: int = 320,
    ) -> None:
        if threshold_chars < 1:
            raise ValueError("threshold_chars must be positive")
        self.store = store
        self.threshold_chars = threshold_chars
        self.preview_chars = preview_chars

    def transform(self, frame: ContextFrame) -> ContextTransform:
        projected = tuple(self._message(message) for message in frame.messages)
        changed = sum(before != after for before, after in zip(frame.messages, projected))
        return ContextTransform(
            replace(frame, messages=projected),
            {"externalized_messages": changed},
        )

    def _message(self, message: AgentMessage) -> AgentMessage:
        if isinstance(message, UserMessage):
            if isinstance(message.content, str):
                return replace(message, content=self._text(message.content, "user"))
            return replace(
                message,
                content=[
                    TextBlock(text=self._text(block.text, "user"))
                    if isinstance(block, TextBlock)
                    else block
                    for block in message.content
                ],
            )
        if isinstance(message, ToolResultMessage):
            return replace(
                message,
                content=[
                    TextBlock(text=self._text(block.text, "tool-result"))
                    if isinstance(block, TextBlock)
                    else block
                    for block in message.content
                ],
            )
        if isinstance(message, AssistantMessage):
            return replace(
                message,
                content=[
                    TextBlock(text=self._text(block.text, "assistant"))
                    if isinstance(block, TextBlock)
                    else block
                    for block in message.content
                ],
            )
        return message

    def _text(self, text: str, origin: str) -> str:
        if len(text) < self.threshold_chars or text.startswith(
            "[External context stored by rlm-ipython]"
        ):
            return text
        artifact = self.store.put_text(text, kind="context", origin=origin)
        preview = text[: self.preview_chars].replace("\x00", "�")
        return (
            "[External context stored by rlm-ipython]\n"
            f"reference: {artifact.reference}\n"
            f"characters: {artifact.characters}\n"
            f"bytes: {artifact.size_bytes}\n"
            f"preview: {preview}\n"
            "Use the preloaded `context` object in the `ipython` tool to "
            "inspect it with context.stat/read/search. Do not infer unseen content "
            "from the preview."
        )


__all__ = ["ProgrammaticContextExternalizer"]
