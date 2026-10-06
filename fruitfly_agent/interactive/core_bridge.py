"""Translate stable Core observation seams into interactive events."""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import Mapping
from typing import Any

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.extensions.hooks import (
    AFTER_TOOL,
    BEFORE_COMPACTION,
    BEFORE_TOOL,
    HookRegistry,
)
from fruitfly_agent.core.context import ContextPipeline
from fruitfly_agent.core.extensions.protocols import Provider
from fruitfly_agent.core.model_stream import (
    AssistantMessageEventStream,
    StreamDone,
    StreamError,
    TextDelta,
    ThinkingDelta,
)

from .dispatch import EventDispatcher
from .events import (
    AssistantTextDelta,
    AssistantThinkingDelta,
    CompactionStarted,
    FrontendEvent,
    RunActivityChanged,
    ToolFinished,
    ToolOutput,
    ToolStarted,
)


class _ObservableProvider:
    """Observe Core stream deltas without changing the Provider contract."""

    def __init__(self, provider: Provider, dispatcher: EventDispatcher) -> None:
        self._provider = provider
        self._dispatcher = dispatcher
        self._request_index = 0

    def begin_run(self) -> None:
        self._request_index = 0

    def __call__(
        self,
        view: Any,
        *,
        signal: asyncio.Event | None = None,
    ) -> AssistantMessageEventStream:
        async def observe():
            saw_text = False
            saw_thinking = False
            self._request_index += 1
            request_index = self._request_index
            model = str(getattr(view, "model", ""))
            await self._activity(
                "waiting_model",
                request_index=request_index,
                subject=model,
                activity_id=f"model-request-{request_index}",
            )
            try:
                inner = self._provider(view, signal=signal)
                async for event in inner:
                    if isinstance(event, TextDelta):
                        if event.text and not saw_text:
                            await self._activity(
                                "receiving_answer",
                                request_index=request_index,
                                subject=model,
                                activity_id=f"model-request-{request_index}",
                            )
                        saw_text = saw_text or bool(event.text)
                        await self._emit(
                            AssistantTextDelta(run_id="", text=event.text)
                        )
                    elif isinstance(event, ThinkingDelta):
                        if event.thinking and not saw_thinking:
                            await self._activity(
                                "receiving_thinking",
                                request_index=request_index,
                                subject=model,
                                activity_id=f"model-request-{request_index}",
                            )
                        saw_thinking = saw_thinking or bool(event.thinking)
                        await self._emit(
                            AssistantThinkingDelta(
                                run_id="",
                                text=event.thinking,
                            )
                        )
                    yield event
                final = await inner.result()
                if not saw_text and final.text:
                    await self._activity(
                        "receiving_answer",
                        request_index=request_index,
                        subject=model,
                        activity_id=f"model-request-{request_index}",
                    )
                    await self._emit(
                        AssistantTextDelta(run_id="", text=final.text)
                    )
                yield StreamDone(result=final)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # Core classifies provider failures.
                yield StreamError(error=exc)

        return AssistantMessageEventStream(observe())

    async def _emit(self, event: FrontendEvent) -> None:
        await self._dispatcher.emit(event)

    async def _activity(
        self,
        phase: str,
        *,
        request_index: int = 0,
        subject: str = "",
        activity_id: str = "",
    ) -> None:
        await self._emit(
            RunActivityChanged(
                run_id="",
                phase=phase,
                request_index=request_index,
                subject=subject,
                activity_id=activity_id,
            )
        )


class CoreEventBridge:
    """Build an observation-only Core config owned by one interactive app."""

    def __init__(
        self,
        dispatcher: EventDispatcher,
        tool_categories: Mapping[str, str] | None = None,
    ) -> None:
        self._dispatcher = dispatcher
        self._tool_categories = dict(tool_categories or {})
        self._observable_provider: _ObservableProvider | None = None

    def begin_run(self) -> None:
        if self._observable_provider is not None:
            self._observable_provider.begin_run()

    def instrument(
        self,
        config: AgentLoopConfig,
        context_pipeline: ContextPipeline | None,
    ) -> tuple[AgentLoopConfig, ContextPipeline | None]:
        source_hooks = config.hooks
        hooks = (
            source_hooks.clone()
            if source_hooks is not None
            else HookRegistry(session=config.session)
        )
        hooks.on(BEFORE_TOOL, self._on_tool_started)
        hooks.on(AFTER_TOOL, self._on_tool_finished)
        hooks.on(BEFORE_COMPACTION, self._on_compaction)

        observable = _ObservableProvider(config.provider, self._dispatcher)
        self._observable_provider = observable
        previous_partial = config.on_partial

        async def on_partial(text: str) -> None:
            await self._dispatcher.emit(ToolOutput(run_id="", text=text))
            if previous_partial is not None:
                result = previous_partial(text)
                if hasattr(result, "__await__"):
                    await result

        observed_config = dataclasses.replace(
            config,
            provider=observable,
            hooks=hooks,
            on_partial=on_partial,
        )
        return observed_config, context_pipeline

    async def _on_tool_started(self, event: Any) -> None:
        await self._dispatcher.emit(
            ToolStarted(
                run_id="",
                tool_call_id=event.tool_call_id,
                tool_name=event.tool_name,
                arguments=dict(event.args),
                category=self._tool_categories.get(event.tool_name, "tools"),
            )
        )
        await self._dispatcher.emit(
            RunActivityChanged(
                run_id="",
                phase="running_tool",
                subject=event.tool_name,
                activity_id=event.tool_call_id,
            )
        )

    async def _on_tool_finished(self, event: Any) -> None:
        output = "".join(
            getattr(block, "text", "") for block in event.result.content
        )
        await self._dispatcher.emit(
            ToolFinished(
                run_id="",
                tool_call_id=event.tool_call_id,
                tool_name=event.tool_name,
                output=output,
                terminate=event.result.terminate,
                category=self._tool_categories.get(event.tool_name, "tools"),
            )
        )
        await self._dispatcher.emit(
            RunActivityChanged(
                run_id="",
                phase="processing_tool_result",
                subject=event.tool_name,
                activity_id=event.tool_call_id,
            )
        )

    async def _on_compaction(self, event: Any) -> None:
        await self._dispatcher.emit(
            CompactionStarted(
                run_id="",
                estimated_tokens=event.estimated_tokens,
                mechanism_id=event.mechanism_id,
                trigger=event.trigger,
            )
        )
        await self._dispatcher.emit(
            RunActivityChanged(
                run_id="",
                phase="compacting",
                subject=event.mechanism_id,
                activity_id=event.mechanism_id,
            )
        )


__all__ = ["CoreEventBridge"]
