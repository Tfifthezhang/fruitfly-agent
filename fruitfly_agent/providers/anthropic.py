"""Anthropic provider adapter — the ONLY file that touches the SDK.

Maps the SDK stream onto our AssistantMessageEventStream protocol and hosts
error classification + retry. Compatible Messages stream behavior handled here:
- full tool_use.input may arrive in content_block_start (no input_json_delta);
- non-standard stop_reason values are normalized to "stop";
- errors are classified as overflow (→ compaction ladder) / retryable / fatal.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict, replace
import json
from typing import TYPE_CHECKING, Any, AsyncIterator, NotRequired, TypedDict, cast

if TYPE_CHECKING:
    from anthropic.types import MessageParam, ToolParam

from fruitfly_agent.core.data_model import (
    AssistantMessage,
    AgentMessage,
    ProviderView,
    TextBlock,
    ThinkingBlock,
    ToolCallBlock,
    Usage,
)
from fruitfly_agent.core.errors import FatalError, OverflowError, RetryableError, TaggedError
from fruitfly_agent.core.model_stream import (
    AssistantMessageEventStream,
    StreamDone,
    StreamError,
    StreamEvent,
    StreamActivity,
    TextDelta,
    ThinkingDelta,
    ToolCallDelta,
    ToolCallEnd,
    ToolCallStart,
)

from .anthropic_codec import convert_to_anthropic
from .media import MediaInput, project_images
from .replay import ReplayBinding, wire_value
from .request_options import validate_request_options
from .services import service_definition
from .error_classification import classify_provider_error
from .transport import TransportPolicy, AttemptDeadline, attempts, close_transport, retry_details, validate_retries

_SERVER_BLOCKS = frozenset({'server_tool_use', 'web_search_tool_result', 'web_fetch_tool_result',
                           'code_execution_tool_result', 'bash_code_execution_tool_result',
                           'text_editor_code_execution_tool_result'})

_STOP_REASON_MAP = {
    "end_turn": "stop",
    "tool_use": "toolUse",
    "max_tokens": "length",
    "refusal": "stop",
}


class _MessageRequest(TypedDict):
    model: str
    system: str
    messages: list[MessageParam]
    max_tokens: int
    tools: NotRequired[list[ToolParam]]

def classify_error(exc: Exception, *, status_code: int | None = None) -> TaggedError:
    """Classify a provider failure. Overflow is NEVER retried — it goes to the ladder."""
    return classify_provider_error(exc, status_code=status_code)


class AnthropicProvider(MediaInput):
    protocol = 'messages'

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str | None = None,
        max_tokens: int = 4096,
        retry_max: int = 3,
        retry_base_delay: float = 1.0,
        connect_timeout: float = 10.0,
        timeout: float = 600.0,
        first_progress_timeout: float = 180.0,
        stall_timeout: float = 180.0,
        total_timeout: float = 900.0,
        cleanup_timeout: float = 5.0,
        retry_jitter: float = 0.2,
        service: str = 'generic',
        vision: bool | None = None,
        **request_options: Any,
    ) -> None:
        import anthropic  # SDK stays in this file.

        request_options = validate_request_options(self.protocol, request_options)
        definition = service_definition(service, self.protocol)
        definition.validate(self.protocol, model, request_options)
        self.request_options = request_options
        self.vision = vision
        self._replay = ReplayBinding(self.protocol, service, base_url, api_key, namespace='anthropic')
        self._anthropic = anthropic
        validate_retries(retry_max, retry_base_delay)
        self._policy = TransportPolicy(connect_timeout, timeout, first_progress_timeout,
                                       stall_timeout, total_timeout, cleanup_timeout, retry_jitter)
        self.transport_parameters = {**asdict(self._policy), "retry_max": retry_max,
                                     "retry_base_delay": retry_base_delay, "transport_version": "bounded-v1"}
        self._client = anthropic.AsyncAnthropic(api_key=api_key, base_url=base_url or definition.base_url, max_retries=0,
                                           timeout=anthropic.Timeout(timeout, connect=connect_timeout))
        self.model = model
        self.max_tokens = max_tokens
        self.retry_max = retry_max
        self.retry_base_delay = retry_base_delay

    async def close(self) -> None:
        """Close the owned SDK client within the cleanup allowance."""
        await close_transport(self._client.close(), self._policy.cleanup_timeout)

    def __call__(
        self, view: ProviderView, *, signal: asyncio.Event | None = None
    ) -> AssistantMessageEventStream:
        """Callable form of stream() — the unified Provider convention."""
        return self.stream(view, signal=signal)

    def stream(
        self, view: ProviderView, *, signal: asyncio.Event | None = None
    ) -> AssistantMessageEventStream:
        """view: the ProviderView request shape."""
        return AssistantMessageEventStream(self._gen(view, signal))

    input_count_supported = False

    def input_estimation_messages(self, view: ProviderView) -> list[AgentMessage]:
        return project_images(view.messages, self.vision)

    def input_measurement_scope(self) -> str:
        import json
        return json.dumps({'protocol': self.protocol, 'service': self._replay.service,
            'model': self.model, 'options': self.request_options,
            'vision': self.vision, 'media_encoding': 'images-v1'}, sort_keys=True)

    def effective_output_limit(self, view: ProviderView) -> int:
        return min(self.max_tokens, view.max_tokens) if view.max_tokens > 0 else self.max_tokens

    def context_usage_tokens(self, usage: Usage) -> int:
        return usage.input_tokens + usage.cache_read_tokens + usage.cache_creation_tokens

    def can_rebase_context(self, before: Any, after: Any) -> bool:
        from .token_counting import can_rebase
        return can_rebase(self, before, after)

    # -- generator -----------------------------------------------------------

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
            await asyncio.wait_for(signal.wait(), timeout=delay)  # abortable sleep
        except asyncio.TimeoutError:
            pass

    # -- one attempt ---------------------------------------------------------

    async def _stream_once(
        self, view: ProviderView, signal: asyncio.Event | None, *, deadline: AttemptDeadline
    ) -> AsyncIterator[StreamEvent]:
        tools = [t.to_schema() for t in view.tools if not t.hide_from_model]
        effective = replace(view, model=view.model or self.model)
        service_definition(self._replay.service, self.protocol).validate(self.protocol, effective.model, self.request_options)
        prefix = convert_to_anthropic(project_images(view.messages, self.vision), replay=self._replay.reader(effective, tools))
        request: dict[str, Any] = {
            "model": view.model or self.model,
            "system": view.system_prompt,
            # The codec owns serialization; this cast describes its SDK wire shape.
            "messages": prefix,
            "max_tokens": min(self.max_tokens, view.max_tokens) if view.max_tokens > 0 else self.max_tokens,
            **self.request_options,
        }
        budget = self.request_options.get('thinking', {}).get('budget_tokens')
        if budget is not None and (type(budget) is not int or not 0 < budget < request['max_tokens']):
            raise FatalError('thinking.budget_tokens must fit inside the request output allowance')
        if tools:
            request["tools"] = cast("list[ToolParam]", tools)

        manager = self._client.messages.stream(**request)
        entered = False
        try:
            sdk_stream = await deadline.wait(manager.__aenter__(), signal)
            entered = True
            iterator = sdk_stream.__aiter__()
            while True:
                try:
                    event = await deadline.wait(iterator.__anext__(), signal)
                except StopAsyncIteration:
                    break
                if getattr(getattr(event, 'delta', None), 'type', None) == 'signature_delta':
                    deadline.progress()
                mapped = self._map_event(event)
                if mapped is not None:
                    meaningful = (isinstance(mapped, ToolCallStart) or
                                  isinstance(mapped, StreamActivity) and bool(mapped.tool_name) or
                                  bool(getattr(mapped, "text", "") or getattr(mapped, "thinking", "") or
                                       getattr(mapped, "json_delta", "")))
                    if meaningful:
                        deadline.progress()
                        yield mapped
            final = await deadline.wait(sdk_stream.get_final_message(), signal)
        except TaggedError:
            raise
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            raise retry_details(exc, classify_error(exc, status_code=status)) from exc
        finally:
            if entered:
                await close_transport(manager.__aexit__(None, None, None), self._policy.cleanup_timeout)
        if final is None:
            raise FatalError('Messages stream ended without a final message')
        message = self._assemble(final)
        items = [{'role': 'assistant', 'content': wire_value(final.content)}]
        yield StreamDone(result=self._replay.attach(message, effective, tools, prefix, items))

    # -- event mapping -------------------------------------------------------

    @staticmethod
    def _map_event(event: Any) -> StreamEvent | None:
        event_type = getattr(event, "type", None)
        if event_type == "content_block_delta":
            delta = event.delta
            delta_type = getattr(delta, "type", None)
            if delta_type == "text_delta":
                return TextDelta(text=delta.text)
            if delta_type == "thinking_delta":
                return ThinkingDelta(thinking=delta.thinking)
            if delta_type == "input_json_delta":
                return ToolCallDelta(json_delta=delta.partial_json)
            return None
        if event_type == "content_block_start":
            block = event.content_block
            if getattr(block, 'type', None) in _SERVER_BLOCKS:
                return StreamActivity('server_tool', tool_name=str(getattr(block, 'name', block.type)),
                    tool_call_id=str(getattr(block, 'id', getattr(block, 'tool_use_id', ''))),
                    tool_status='started' if block.type == 'server_tool_use' else 'completed')
            if getattr(block, "type", None) == "tool_use":
                # Compatible streams may deliver the complete input in this event.
                return ToolCallStart(
                    id=block.id,
                    name=block.name,
                    input=dict(block.input or {}),
                )
            return None
        if event_type == "content_block_stop":
            return None
        return None

    @staticmethod
    def _assemble(final: Any) -> AssistantMessage:
        blocks: list[TextBlock | ThinkingBlock | ToolCallBlock] = []
        for block in getattr(final, "content", []) or []:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                blocks.append(TextBlock(text=block.text))
            elif block_type == "thinking":
                blocks.append(ThinkingBlock(thinking=block.thinking))
            elif block_type == "tool_use":
                input_raw = block.input
                if isinstance(input_raw, str):
                    try:
                        input_raw = json.loads(input_raw) or {}
                    except json.JSONDecodeError:
                        input_raw = {}
                blocks.append(
                    ToolCallBlock(id=block.id, name=block.name, input=dict(input_raw or {}))
                )
            elif block_type not in _SERVER_BLOCKS | {'redacted_thinking'}:
                raise FatalError('Unsupported Messages content block: ' + str(block_type))
        stop = str(getattr(final, "stop_reason", None) or "end_turn")
        stop_reason = _STOP_REASON_MAP.get(stop, "stop")
        usage = getattr(final, "usage", None)
        usage_obj = None
        if usage is not None:
            usage_obj = Usage(
                input_tokens=getattr(usage, "input_tokens", 0) or 0,
                output_tokens=getattr(usage, "output_tokens", 0) or 0,
                cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
                cache_creation_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
            )
        return AssistantMessage(
            content=blocks,
            stop_reason=stop_reason,  # type: ignore[arg-type]
            usage=usage_obj,
            continue_turn=stop == 'pause_turn',
        )


__all__ = ["AnthropicProvider", "classify_error"]
