"""UI-independent interactive application layer over the stable Core loop."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Awaitable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Callable

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.data_model import AgentLoopResult, AgentMessage, UserMessage
from fruitfly_agent.core.context import ContextPipeline
from fruitfly_agent.core.extensions.protocols import SessionLike
from fruitfly_agent.core.loop import run_agent_loop

from .core_bridge import CoreEventBridge
from .dispatch import EventDispatcher, EventSink
from .events import (
    InteractiveEvent,
    RunActivityChanged,
    RunFinished,
    RunStarted,
)
from .models import InteractiveMechanism, InteractiveStatus


RunLoop = Callable[..., Awaitable[AgentLoopResult]]


class InteractiveSession:
    """Own conversation state and expose prompt/events instead of terminal I/O."""

    def __init__(
        self,
        config: AgentLoopConfig,
        *,
        context_pipeline: ContextPipeline | None = None,
        messages: Sequence[AgentMessage] = (),
        working_directory: str | Path = ".",
        session_path: str | Path = "",
        mechanisms: Sequence[str] = (),
        mechanism_details: Sequence[InteractiveMechanism] = (),
        tool_categories: Mapping[str, str] | None = None,
        event_sink: EventSink | None = None,
        run_loop: RunLoop = run_agent_loop,
        trace_capacity: int = 200,
    ) -> None:
        self._messages = list(messages)
        self._run_loop = run_loop
        self._working_directory = str(Path(working_directory).resolve())
        self._session_path = str(session_path)
        self._mechanisms = tuple(mechanisms)
        self._mechanism_details = tuple(mechanism_details)
        self._run_lock = asyncio.Lock()
        self._active_signal: asyncio.Event | None = None
        self._accepting_steering = False
        self._steering: deque[UserMessage] = deque()
        self._dispatcher = EventDispatcher(
            event_sink,
            trace_capacity=trace_capacity,
        )
        self._bridge = CoreEventBridge(self._dispatcher, tool_categories)
        self._config, self._context_pipeline = self._bridge.instrument(
            self._with_interactive_steering(config),
            context_pipeline,
        )

    def canonical_items(self):
        """Committed messages with IDs; UI drafts never alter this transcript."""
        if self._config.session is not None:
            return tuple(self._config.session.context_items())
        from fruitfly_agent.core.data_model import ContextItem
        return tuple(ContextItem(id=f"memory:{i}", message=m) for i,m in enumerate(self._messages))

    @property
    def messages(self) -> list[AgentMessage]:
        return list(self._messages)

    @property
    def status(self) -> InteractiveStatus:
        return InteractiveStatus(
            model=self._config.model,
            working_directory=self._working_directory,
            session_path=self._session_path,
            message_count=len(self._messages),
            tool_names=tuple(tool.name for tool in self._config.tools or ()),
            mechanisms=self._mechanisms,
            mechanism_details=self._mechanism_details,
        )

    def set_event_sink(self, sink: EventSink | None) -> None:
        self._dispatcher.set_sink(sink)

    def trace(self, limit: int = 12) -> list[InteractiveEvent]:
        return self._dispatcher.trace(limit)

    @property
    def running(self) -> bool:
        return self._active_signal is not None

    def cancel(self) -> bool:
        """Request cooperative cancellation at the next Core safe point."""

        if self._active_signal is None:
            return False
        self._active_signal.set()
        return True

    def steer(self, prompt: str) -> bool:
        """Inject one user message before the next Provider request."""

        prompt = prompt.strip()
        if not prompt:
            raise ValueError("steering prompt must not be empty")
        if self._active_signal is None or not self._accepting_steering:
            return False
        self._steering.append(UserMessage(content=prompt))
        return True

    async def submit(self, prompt: str) -> AgentLoopResult:
        prompt = prompt.strip()
        if not prompt:
            raise ValueError("prompt must not be empty")
        async with self._run_lock:
            signal = asyncio.Event()
            self._active_signal = signal
            self._accepting_steering = True
            self._dispatcher.begin_run()
            self._bridge.begin_run()
            try:
                user_message = UserMessage(content=prompt)
                self._append_user_message(user_message)
                self._messages.append(user_message)
                await self._dispatcher.emit(
                    RunStarted(
                        run_id="",
                        prompt=prompt,
                        model=self._config.model,
                        message_count=len(self._messages),
                    )
                )
                result = await self._run_loop(
                    self._config,
                    self._messages,
                    signal=signal,
                    context_pipeline=self._context_pipeline,
                )
                self._accepting_steering = False
                self._active_signal = None
                self._messages = list(result.messages)
                await self._dispatcher.emit(
                    RunActivityChanged(
                        run_id="",
                        phase="finalizing",
                    )
                )
                await self._dispatcher.emit(
                    RunFinished(
                        run_id="",
                        stop_reason=result.stop_reason,
                        model=result.model,
                        turn_count=result.turn_count,
                        tool_call_count=result.tool_call_count,
                        input_tokens=result.usage.input_tokens,
                        output_tokens=result.usage.output_tokens,
                        is_error=result.is_error,
                        error_details=result.error_details,
                    )
                )
                return result
            finally:
                self._active_signal = None
                self._accepting_steering = False
                self._steering.clear()
                self._dispatcher.end_run()

    def _with_interactive_steering(
        self,
        config: AgentLoopConfig,
    ) -> AgentLoopConfig:
        previous = config.get_steering_messages
        previous_follow_up = config.get_follow_up_messages

        async def drain(context) -> list[AgentMessage]:
            messages: list[AgentMessage] = []
            if previous is not None:
                result = previous(context)
                if hasattr(result, "__await__"):
                    result = await result
                messages.extend(result)
            while self._steering:
                messages.append(self._steering.popleft())
            return messages

        async def follow_up(context) -> list[AgentMessage]:
            messages: list[AgentMessage] = []
            if previous_follow_up is not None:
                result = previous_follow_up(context)
                if hasattr(result, "__await__"):
                    result = await result
                messages.extend(result)
            # Input received during the final model response still belongs to
            # this run. A follow-up causes Core to make another request.
            while self._steering:
                messages.append(self._steering.popleft())
            if not messages:
                self._accepting_steering = False
            return messages

        return replace(
            config,
            get_steering_messages=drain,
            get_follow_up_messages=follow_up,
        )

    def _append_user_message(self, message: UserMessage) -> None:
        session: SessionLike | None = self._config.session
        if session is not None:
            session.append("message", {"message": message.to_dict()})


__all__ = ["EventSink", "InteractiveSession", "InteractiveStatus"]
