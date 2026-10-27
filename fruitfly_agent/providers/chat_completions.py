"""Chat Completions adapter using the common bounded transport and replay ports."""
from __future__ import annotations

from dataclasses import replace
import json
from typing import Any, AsyncIterator
import asyncio

from fruitfly_agent.core.data_model import AssistantMessage, ProviderView, TextBlock, ThinkingBlock, ToolCallBlock, Usage
from fruitfly_agent.core.errors import FatalError, TaggedError
from fruitfly_agent.core.model_stream import StreamEvent, StreamDone, TextDelta, ThinkingDelta, ToolCallStart, ToolCallDelta
from .openai import OpenAIProvider, classify_error
from .chat_codec import convert_to_chat
from .replay import wire_value
from .transport import AttemptDeadline, close_transport, retry_details


class ChatCompletionsProvider(OpenAIProvider):
    protocol = 'chat-completions'
    continuation_namespace = 'openai-chat'

    async def _stream_once(self, view: ProviderView, signal: asyncio.Event | None,
                           *, deadline: AttemptDeadline) -> AsyncIterator[StreamEvent]:
        effective = replace(view, model=view.model or self.model)
        self._service.validate(self.protocol, effective.model, self.request_options)
        tools = [{'type': 'function', 'function': {'name': t.name, 'description': t.description,
                  'parameters': t.parameters}} for t in view.tools if not t.hide_from_model]
        prefix = convert_to_chat(view.messages, replay=self._replay.reader(effective, tools))
        token_field = self._service.chat_token_field
        request: dict[str, Any] = {**self.request_options, 'model': effective.model,
            'messages': [{'role': 'system', 'content': view.system_prompt}, *prefix],
            token_field: min(self.max_output_tokens, view.max_tokens) if view.max_tokens > 0 else self.max_output_tokens}
        if self._service.chat_stream_usage:
            request['stream_options'] = {'include_usage': True}
        if tools:
            request['tools'] = tools
            if self._service.parallel_control:
                request['parallel_tool_calls'] = self.parallel_tool_calls
        text: list[str] = []
        thinking: list[str] = []
        refusal: list[str] = []
        calls: dict[int, dict[str, Any]] = {}
        finish: str | None = None
        usage = None
        stream = None
        try:
            stream = await deadline.wait(self._client.chat.completions.create(**request, stream=True), signal)
            iterator = stream.__aiter__()
            while True:
                try:
                    chunk = await deadline.wait(iterator.__anext__(), signal)
                except StopAsyncIteration:
                    break
                if getattr(chunk, 'usage', None) is not None:
                    usage = chunk.usage
                for choice in getattr(chunk, 'choices', []) or []:
                    if getattr(choice, 'index', 0) != 0:
                        raise FatalError('Chat Completions supports one candidate per request')
                    finish = getattr(choice, 'finish_reason', None) or finish
                    delta = choice.delta
                    unknown = {key for key, value in wire_value(delta).items() if value
                        and key not in {'role', 'content', 'reasoning_content', 'refusal', 'tool_calls'}}
                    if unknown:
                        raise FatalError('Unsupported Chat Completions delta fields: ' + ', '.join(sorted(unknown)))
                    for name, target, event_type in (('content', text, TextDelta),
                            ('reasoning_content', thinking, ThinkingDelta), ('refusal', refusal, TextDelta)):
                        part = getattr(delta, name, None)
                        if part:
                            if not isinstance(part, str):
                                raise FatalError('Unsupported Chat Completions delta: ' + name)
                            target.append(part)
                            deadline.progress()
                            yield event_type(part)
                    for part in getattr(delta, 'tool_calls', []) or []:
                        index = int(part.index)
                        if index not in calls:
                            calls[index] = {'id': '', 'type': 'function', 'function': {'name': '', 'arguments': ''}}
                        call = calls[index]
                        if getattr(part, 'id', None):
                            call['id'] = part.id
                        function = getattr(part, 'function', None)
                        if function is not None:
                            if getattr(function, 'name', None):
                                call['function']['name'] += function.name
                                deadline.progress()
                                yield ToolCallStart(call['id'], call['function']['name'])
                            if getattr(function, 'arguments', None):
                                call['function']['arguments'] += function.arguments
                                deadline.progress()
                                yield ToolCallDelta(function.arguments)
                        # Preserve protocol extension metadata attached to tool calls.
                        for key, value in wire_value(part).items():
                            if key not in {'index', 'id', 'type', 'function'} and value is not None:
                                call[key] = value
        except TaggedError:
            raise
        except Exception as exc:
            raise retry_details(exc, classify_error(exc, status_code=getattr(exc, 'status_code', None))) from exc
        finally:
            if stream is not None:
                await close_transport(stream.close(), self._policy.cleanup_timeout)
        if finish not in {'stop', 'tool_calls', 'length', 'content_filter'}:
            raise FatalError('Chat Completions stream ended without a supported finish reason')
        blocks: list[Any] = []
        if thinking:
            blocks.append(ThinkingBlock(''.join(thinking)))
        if text or refusal:
            blocks.append(TextBlock(''.join(text + refusal)))
        for call in calls.values():
            if not call['id'] or not call['function']['name']:
                raise FatalError('Incomplete Chat Completions tool call')
            try:
                arguments = json.loads(call['function']['arguments'] or '{}')
            except (ValueError, TypeError):
                arguments = {}
            blocks.append(ToolCallBlock(call['id'], call['function']['name'], arguments if isinstance(arguments, dict) else {}))
        details = getattr(usage, 'completion_tokens_details', None)
        receipt = None if usage is None else Usage(
            input_tokens=int(getattr(usage, 'prompt_tokens', 0) or 0),
            output_tokens=int(getattr(usage, 'completion_tokens', 0) or 0),
            cache_read_tokens=int(getattr(getattr(usage, 'prompt_tokens_details', None), 'cached_tokens', 0) or 0),
            reasoning_tokens=getattr(details, 'reasoning_tokens', None))
        message = AssistantMessage(content=blocks, usage=receipt,
            stop_reason='length' if finish == 'length' else 'toolUse' if calls else 'stop')
        item: dict[str, Any] = {'role': 'assistant', 'content': ''.join(text) or None}
        if thinking:
            item['reasoning_content'] = ''.join(thinking)
        if refusal:
            item['refusal'] = ''.join(refusal)
        if calls:
            item['tool_calls'] = list(calls.values())
        yield StreamDone(result=self._replay.attach(message, effective, tools, prefix, [item]))


__all__ = ['ChatCompletionsProvider']
