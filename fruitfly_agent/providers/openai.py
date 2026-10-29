"""OpenAI Responses API adapter for the frozen Provider protocol."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, replace
import json
from typing import Any, AsyncIterator

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
    ToolCallStart,
)
from .openai_codec import convert_to_openai
from .media import MediaInput, project_images
from .replay import ReplayBinding, wire_value
from .request_options import validate_request_options
from .services import service_definition
from .error_classification import classify_provider_error
from .transport import TransportPolicy, AttemptDeadline, attempts, close_transport, retry_details, validate_retries

_SERVER_ITEMS = frozenset({'web_search_call', 'file_search_call', 'code_interpreter_call'})


def classify_error(exc: Exception, *, status_code: int | None = None) -> TaggedError:
    return classify_provider_error(exc, status_code=status_code)


class OpenAIProvider(MediaInput):
    """Map OpenAI streaming events to FruitFlyAgent's provider-neutral stream."""

    protocol = 'responses'
    continuation_namespace = 'openai'

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
        service: str = 'generic',
        vision: bool | None = None,
        **request_options: Any,
    ) -> None:
        import openai  # SDK stays inside the adapter.

        request_options = validate_request_options(self.protocol, request_options)
        self._service = service_definition(service, self.protocol)
        self._service.validate(self.protocol, model, request_options)
        self.service = service
        self.vision = vision
        self._replay = ReplayBinding(self.protocol, service, base_url, api_key,
                                    namespace=self.continuation_namespace)
        validate_retries(retry_max, retry_base_delay)
        self._policy = TransportPolicy(connect_timeout, timeout, first_progress_timeout,
                                       stall_timeout, total_timeout, cleanup_timeout, retry_jitter)
        self.transport_parameters = {**asdict(self._policy), "retry_max": retry_max,
                                     "retry_base_delay": retry_base_delay, "transport_version": "bounded-v1"}
        self._client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url or self._service.base_url, max_retries=0,
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

    def _prepare_payload(self, view: ProviderView) -> tuple[dict[str, Any], ProviderView, list[dict[str, Any]], list[dict[str, Any]]]:
        request: dict[str, Any] = {
            "model": view.model or self.model,
            "instructions": view.system_prompt,
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
        if not self._service.parallel_control:
            request.pop('parallel_tool_calls')
        if not self._service.responses_store:
            request.pop('store')
        effective = replace(view, model=view.model or self.model)
        self._service.validate(self.protocol, effective.model, self.request_options)
        prefix = convert_to_openai(project_images(view.messages, self.vision), replay=self._replay.reader(effective, tools))
        request['input'] = prefix

        return request, effective, tools, prefix

    @property
    def input_count_supported(self) -> bool:
        from .token_counting import supports_count
        return supports_count(self)

    def input_estimation_messages(self, view: ProviderView) -> list[AgentMessage]:
        return project_images(view.messages, self.vision)

    def effective_output_limit(self, view: ProviderView) -> int:
        return min(self.max_output_tokens, view.max_tokens) if view.max_tokens > 0 else self.max_output_tokens

    def context_usage_tokens(self, usage: Usage) -> int:
        return usage.input_tokens

    def can_rebase_context(self, before: Any, after: Any) -> bool:
        from .token_counting import can_rebase
        return can_rebase(self, before, after)

    def input_count_identity(self, view: ProviderView) -> str:
        import hashlib
        import json
        request, _, _, _ = self._prepare_payload(view)
        return hashlib.sha256(json.dumps(request, sort_keys=True, default=str).encode()).hexdigest()

    def input_measurement_scope(self) -> str:
        import json
        return json.dumps({'protocol': self.protocol, 'service': self.service,
            'model': self.model, 'options': self.request_options,
            'vision': self.vision, 'media_encoding': 'images-v1'}, sort_keys=True)

    async def count_input(self, view: ProviderView, *, signal: asyncio.Event | None = None) -> int:
        if not self.input_count_supported:
            raise ValueError('input counting is not declared for this service/protocol')
        if signal is not None and signal.is_set():
            raise asyncio.CancelledError
        from .token_counting import OPENAI_COUNT_FIELDS
        request, _, _, _ = self._prepare_payload(view)
        payload = {key: value for key, value in request.items() if key in OPENAI_COUNT_FIELDS}
        result = await self._client.responses.input_tokens.count(**payload)
        if signal is not None and signal.is_set():
            raise asyncio.CancelledError
        value = result.input_tokens
        if type(value) is not int or value < 0:
            raise ValueError('invalid input token count')
        return value

    async def _stream_once(
        self, view: ProviderView, signal: asyncio.Event | None, *, deadline: AttemptDeadline
    ) -> AsyncIterator[StreamEvent]:
        request, effective, tools, prefix = self._prepare_payload(view)

        text_parts: list[str] = []
        thoughts: list[str] = []
        done_items: dict[int, dict[str, Any]] = {}
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
                        thoughts.append(delta)
                        deadline.progress()
                        yield ThinkingDelta(thinking=delta)
                elif event_type == 'response.output_item.done':
                    done_items[int(getattr(event, 'output_index', len(done_items)))] = wire_value(event.item)
                    deadline.progress()
                    if getattr(event.item, 'type', '') in _SERVER_ITEMS:
                        yield StreamActivity('server_tool', tool_name=event.item.type,
                            tool_call_id=str(getattr(event.item, 'id', '')), tool_status='completed')
                elif event_type == "response.output_item.added":
                    item = getattr(event, "item", None)
                    if getattr(item, 'type', '') in _SERVER_ITEMS:
                        deadline.progress()
                        yield StreamActivity('server_tool', tool_name=str(getattr(item, 'type', '')),
                            tool_call_id=str(getattr(item, 'id', '')), tool_status='started')
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
        if completed is None:
            raise FatalError('Responses stream ended without a terminal response')
        output = getattr(completed, 'output', None)
        if output is None and done_items:
            output = [done_items[key] for key in sorted(done_items)]
        message = self._assemble(completed, text_parts, calls, output=output)
        if output is None:
            if thoughts:
                message = replace(message, content=[ThinkingBlock(''.join(thoughts)), *message.content])
            output = convert_to_openai([message])
            if thoughts:
                output.insert(0, {'type': 'reasoning', 'content': [{'type': 'reasoning_text', 'text': ''.join(thoughts)}]})
        message = self._replay.attach(message, effective, tools, prefix, wire_value(output))
        yield StreamDone(result=message)

    @staticmethod
    def _assemble(
        response: Any, text_parts: list[str], calls: dict[str, dict[str, str]], *, output: Any = None,
    ) -> AssistantMessage:
        blocks: list[TextBlock | ThinkingBlock | ToolCallBlock] = []
        if output is None:
            output = getattr(response, 'output', None)
        if output is not None:
            for item in wire_value(output):
                kind = item.get('type')
                if kind == 'message':
                    for part in item.get('content', []):
                        if part.get('type') == 'output_text':
                            blocks.append(TextBlock(part.get('text', '')))
                        elif part.get('type') == 'refusal':
                            blocks.append(TextBlock(part.get('refusal', '')))
                        else:
                            raise FatalError('Unsupported Responses message content: ' + str(part.get('type')))
                elif kind == 'reasoning':
                    for part in item.get('content', []) or item.get('summary', []):
                        text = part.get('text', '')
                        if text:
                            blocks.append(ThinkingBlock(text))
                elif kind == 'function_call':
                    try:
                        arguments = json.loads(item.get('arguments') or '{}')
                    except (json.JSONDecodeError, TypeError):
                        arguments = {}
                    blocks.append(ToolCallBlock(item.get('call_id', ''), item.get('name', ''),
                                                arguments if isinstance(arguments, dict) else {}))
                elif kind in _SERVER_ITEMS:
                    continue
                else:
                    raise FatalError('Unsupported Responses output item: ' + str(kind))
        elif text_parts:
            blocks.append(TextBlock(text="".join(text_parts)))
        for item_id, call in (calls.items() if output is None else ()):
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
            reasoning_tokens=getattr(getattr(usage, 'output_tokens_details', None), 'reasoning_tokens', None),
        )
        incomplete = getattr(response, "incomplete_details", None)
        reason = getattr(incomplete, "reason", None)
        stop_reason = 'length' if reason == 'max_output_tokens' else 'toolUse' if any(isinstance(b, ToolCallBlock) for b in blocks) else 'stop'
        phases = [item.get('phase') for item in wire_value(output or []) if item.get('type') == 'message']
        return AssistantMessage(content=blocks, stop_reason=stop_reason, usage=usage_obj,  # type: ignore[arg-type]
            continue_turn=bool(phases and phases[-1] == 'commentary' and stop_reason == 'stop'))


__all__ = ["OpenAIProvider", "classify_error"]
