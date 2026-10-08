"""OpenAI Responses API adapter for the frozen Provider protocol."""

from __future__ import annotations

import asyncio
from dataclasses import asdict
import json
from typing import Any, AsyncIterator

from fruitfly_agent.core.data_model import (
    AssistantMessage,
    ProviderView,
    TextBlock,
    ToolCallBlock,
    Usage,
)
from fruitfly_agent.core.errors import FatalError, OverflowError, RetryableError, TaggedError
from fruitfly_agent.core.model_stream import (
    AssistantMessageEventStream,
    StreamDone,
    StreamError,
    StreamEvent,
    TextDelta,
    ThinkingDelta,
    ToolCallDelta,
    ToolCallStart,
)
from .openai_codec import convert_to_openai
from .error_classification import classify_provider_error
from .transport import TransportPolicy, AttemptDeadline, attempts, close_transport, retry_details, validate_retries


def classify_error(exc: Exception, *, status_code: int | None = None) -> TaggedError:
    return classify_provider_error(exc, status_code=status_code)


class OpenAIProvider:
    """Map OpenAI streaming events to FruitFlyAgent's provider-neutral stream."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str | None = None,
        max_output_tokens: int = 4096,
        retry_max: int = 3,
        retry_base_delay: float = 1.0,
        connect_timeout: float = 10.0,
        timeout: float = 600.0,
        first_progress_timeout: float = 180.0,
        stall_timeout: float = 180.0,
        total_timeout: float = 900.0,
        cleanup_timeout: float = 5.0,
        retry_jitter: float = 0.2,
        store: bool = False,
        parallel_tool_calls: bool = True,
        **request_options: Any,
    ) -> None:
        import openai  # SDK stays inside the adapter.

        validate_retries(retry_max, retry_base_delay)
        self._policy = TransportPolicy(connect_timeout, timeout, first_progress_timeout,
                                       stall_timeout, total_timeout, cleanup_timeout, retry_jitter)
        self.transport_parameters = {**asdict(self._policy), "retry_max": retry_max,
                                     "retry_base_delay": retry_base_delay, "transport_version": "bounded-v1"}
        self._client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url, max_retries=0,
                                           timeout=openai.Timeout(timeout, connect=connect_timeout))
        self.model = model
        self.max_output_tokens = max_output_tokens
        self.retry_max = retry_max
        self.retry_base_delay = retry_base_delay
        self.store = store
        self.parallel_tool_calls = parallel_tool_calls
        self.request_options = request_options

    async def close(self) -> None:
        """Close the owned SDK client within the cleanup allowance."""
        await close_transport(self._client.close(), self._policy.cleanup_timeout)

    def __call__(
        self, view: ProviderView, *, signal: asyncio.Event | None = None
    ) -> AssistantMessageEventStream:
        return AssistantMessageEventStream(self._gen(view, signal))

    async def _gen(
        self, view: ProviderView, signal: asyncio.Event | None
    ) -> AsyncIterator[StreamEvent]:
        producer = attempts(self, view, signal)
        try:
            async for event in producer:
                yield event
        finally:
            await producer.aclose()

    async def _sleep(self, delay: float, signal: asyncio.Event | None) -> None:
        if signal is None:
            await asyncio.sleep(delay)
            return
        try:
            await asyncio.wait_for(signal.wait(), timeout=delay)
        except asyncio.TimeoutError:
            pass

    async def _stream_once(
        self, view: ProviderView, signal: asyncio.Event | None, *, deadline: AttemptDeadline
    ) -> AsyncIterator[StreamEvent]:
        request: dict[str, Any] = {
            "model": view.model or self.model,
            "instructions": view.system_prompt,
            "input": convert_to_openai(view.messages),
            "max_output_tokens": min(self.max_output_tokens, view.max_tokens) if view.max_tokens > 0 else self.max_output_tokens,
            "store": self.store,
            "parallel_tool_calls": self.parallel_tool_calls,
            **self.request_options,
        }
        tools = [
            {
                "type": "function",
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
                "strict": False,
            }
            for tool in view.tools
            if not tool.hide_from_model
        ]
        if tools:
            request["tools"] = tools

        text_parts: list[str] = []
        calls: dict[str, dict[str, str]] = {}
        completed: Any = None
        stream = None
        try:
            stream = await deadline.wait(self._client.responses.create(**request, stream=True), signal)
            iterator = stream.__aiter__()
            while True:
                try:
                    event = await deadline.wait(iterator.__anext__(), signal)
                except StopAsyncIteration:
                    break
                if signal is not None and signal.is_set():
                    raise asyncio.CancelledError
                event_type = getattr(event, "type", "")
                if event_type == "response.output_text.delta":
                    delta = str(getattr(event, "delta", ""))
                    text_parts.append(delta)
                    if delta:
                        deadline.progress()
                        yield TextDelta(text=delta)
                elif event_type in {"response.reasoning_text.delta", "response.reasoning_summary_text.delta"}:
                    delta = str(getattr(event, "delta", ""))
                    if delta:
                        deadline.progress()
                        yield ThinkingDelta(thinking=delta)
                elif event_type == "response.output_item.added":
                    item = getattr(event, "item", None)
                    if getattr(item, "type", "") == "function_call":
                        call_id = str(getattr(item, "call_id", None) or getattr(item, "id", ""))
                        item_id = str(getattr(item, "id", "") or call_id)
                        calls[item_id] = {
                            "id": call_id,
                            "name": str(getattr(item, "name", "")),
                            "arguments": str(getattr(item, "arguments", "") or ""),
                        }
                        deadline.progress()
                        yield ToolCallStart(id=call_id, name=calls[item_id]["name"])
                elif event_type == "response.function_call_arguments.delta":
                    call_id = str(getattr(event, "item_id", ""))
                    delta = str(getattr(event, "delta", ""))
                    calls.setdefault(
                        call_id, {"id": call_id, "name": "", "arguments": ""}
                    )["arguments"] += delta
                    if delta:
                        deadline.progress()
                        yield ToolCallDelta(json_delta=delta)
                elif event_type == "response.function_call_arguments.done":
                    item_id = str(getattr(event, "item_id", ""))
                    call = calls.setdefault(
                        item_id,
                        {
                            "id": str(getattr(event, "call_id", "") or item_id),
                            "name": str(getattr(event, "name", "")),
                            "arguments": "",
                        },
                    )
                    if not call["arguments"]:
                        call["arguments"] = str(getattr(event, "arguments", "") or "")
                    if not call["name"]:
                        call["name"] = str(getattr(event, "name", ""))
                elif event_type == "response.completed":
                    completed = getattr(event, "response", None)
                elif event_type == "response.incomplete":
                    completed = getattr(event, "response", None)
                elif event_type in ("response.failed", "error"):
                    detail = getattr(event, "error", None) or getattr(event, "response", None)
                    raise FatalError(f"OpenAI response failed: {detail}")
        except TaggedError:
            raise
        except Exception as exc:  # noqa: BLE001
            status = getattr(exc, "status_code", None)
            raise retry_details(exc, classify_error(exc, status_code=status)) from exc
        finally:
            if stream is not None:
                await close_transport(stream.close(), self._policy.cleanup_timeout)
        # StreamDone ends consumption; close the transport before emitting it.
        yield StreamDone(result=self._assemble(completed, text_parts, calls))

    @staticmethod
    def _assemble(
        response: Any, text_parts: list[str], calls: dict[str, dict[str, str]]
    ) -> AssistantMessage:
        blocks: list[TextBlock | ToolCallBlock] = []
        if text_parts:
            blocks.append(TextBlock(text="".join(text_parts)))
        for item_id, call in calls.items():
            try:
                arguments = json.loads(call["arguments"] or "{}")
            except (json.JSONDecodeError, TypeError):
                arguments = {}
            blocks.append(ToolCallBlock(id=call.get("id", item_id), name=call["name"], input=arguments))
        usage = getattr(response, "usage", None)
        input_details = getattr(usage, "input_tokens_details", None)
        usage_obj = None if usage is None else Usage(
            input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            cache_read_tokens=int(getattr(input_details, "cached_tokens", 0) or 0),
        )
        incomplete = getattr(response, "incomplete_details", None)
        reason = getattr(incomplete, "reason", None)
        stop_reason = "toolUse" if calls else ("length" if reason == "max_output_tokens" else "stop")
        return AssistantMessage(content=blocks, stop_reason=stop_reason, usage=usage_obj)  # type: ignore[arg-type]


__all__ = ["OpenAIProvider", "classify_error"]
