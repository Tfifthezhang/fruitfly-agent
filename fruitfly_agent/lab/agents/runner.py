"""Compose independent role invocations over the public Core loop."""
from dataclasses import asdict, replace
import time
from uuid import uuid4

from fruitfly_agent.core.context.budget import forward_context_capabilities
from fruitfly_agent.core.loop import run_agent_loop
from fruitfly_agent.core.model_stream import AssistantMessageEventStream, StreamDone


class AgentRunner:
    def __init__(self, config):
        self.config = config

    async def run(self, messages, *, tools=(), system_prompt=None, signal=None, observe=None, record=None):
        record = record or (lambda *args, **kwargs: None)
        observe = observe or (lambda *args: None)
        config = self.config
        def provider(view, *, signal=None):
            request_id, started = uuid4().hex, time.monotonic()
            observe('model')
            record('request', id=request_id, model=view.model)
            async def events():
                inner = None
                try:
                    inner = config.provider(view, signal=signal)
                    async for event in inner:
                        yield event
                    message = await inner.result()
                    record('response', attempt_id=request_id, status='completed', text=message.text,
                        usage=message.usage.to_dict() if message.usage else None,
                        elapsed_seconds=time.monotonic() - started)
                    yield StreamDone(message)
                except BaseException:
                    record('response', attempt_id=request_id, status='interrupted',
                        usage=None, elapsed_seconds=time.monotonic() - started)
                    raise
                finally:
                    if inner is not None:
                        await inner.aclose()
            return AssistantMessageEventStream(events())
        forward_context_capabilities(provider, config.provider)
        invocation = replace(config, provider=provider, tools=tuple(tools), session=None,
            system_prompt=config.system_prompt if system_prompt is None else system_prompt,
            max_turns=None, max_tool_calls_per_turn=None,
            get_follow_up_messages=None, get_steering_messages=None)
        result = await run_agent_loop(invocation, list(messages), signal=signal)
        record('agent-finished', usage=result.usage.to_dict(),
            diagnostics=asdict(result.diagnostics) if result.diagnostics is not None else None,
            status='error' if result.is_error else result.stop_reason)
        return result
