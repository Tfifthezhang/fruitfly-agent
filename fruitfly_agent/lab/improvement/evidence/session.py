"""Compose workspace access with a shared Agent invocation; roles own policy."""
from dataclasses import replace
from contextlib import AsyncExitStack
from fruitfly_agent.core.context.budget import forward_context_capabilities
from fruitfly_agent.core.model_stream import AssistantMessageEventStream, StreamDone
from fruitfly_agent.lab.context_manager.measurement import new_measurement_scope
from fruitfly_agent.lab.context_manager.measurement.budget import MeasurementService
from fruitfly_agent.core.data_model import AssistantMessage, UserMessage
from fruitfly_agent.lab.agents import AgentRunner
from .access import EvidenceAccess
from .tools import evidence_tools
from .configuration import EvidenceSettings


class EvidenceSession:
    def __init__(self, config, artifacts, *, settings=None, reader_factory=None, runtime_factory=None):
        self.config, self.artifacts = config, artifacts
        self.settings = EvidenceSettings.from_dict(settings)
        self.reader_factory = reader_factory
        self.runtime_factory = runtime_factory

    async def session(self, mission, workspace, services, *, writable=False, system='', submit=None, initial_content=None, extra_tools=(), validate_final=None, submission_result=None, editing_instructions=None, editing_options=None):
        if not hasattr(workspace,'access'):
            raise ValueError('workspace must provide evidence access receipts')
        workspace.record=services.record
        workspace.access.record=services.record
        submitted=None
        def seal(value):
            nonlocal submitted
            submit(value)
            import json
            submitted=json.dumps(value,ensure_ascii=False)
        reader = self.reader_factory(workspace, settings=self.settings) if self.reader_factory else None
        tools=list(evidence_tools(workspace,settings=self.settings,reader=reader))
        if writable:
            from ..editor.tools import editing_tools
            tools.extend(editing_tools(workspace,submit=seal if submit is not None else None,settings=self.settings, instructions=editing_instructions, options=editing_options))
        tools.extend(extra_tools)
        def prepare_config(config, *, delegated=False):
            meter = new_measurement_scope(config.context_meter) or MeasurementService()
            def bounded_provider(view, *, signal=None):
                async def events():
                    services.check()
                    workspace.access.budget['model_requests'] += 1
                    if workspace.access.budget['model_requests'] > self.settings.supply.max_pages + self.settings.supply.completion_requests:
                        raise RuntimeError('evidence_request_budget_exhausted: shared role request budget exhausted')
                    if delegated:
                        services.observe('model')
                    measurement = await meter.measure(view, config.provider, signal=signal)
                    if not measurement.fits(config.context_window):
                        services.record('evidence-context-budget-exhausted', input_tokens=measurement.input_tokens,
                            output_reserve=measurement.output_reserve, quality=measurement.quality)
                        raise RuntimeError('evidence_context_budget_exhausted: input and output reserve exceed context window')
                    inner = config.provider(view, signal=signal)
                    try:
                        async for event in inner:
                            yield event
                        yield StreamDone(await inner.result())
                    finally:
                        await inner.aclose()
                return AssistantMessageEventStream(events())
            forward_context_capabilities(bounded_provider, config.provider)
            return replace(config, provider=bounded_provider)
        role_config = prepare_config(replace(self.config, env=None, hooks=None,
            prepare_next_turn=None, before_tool_call=None, after_tool_call=None,
            on_partial=None, on_tool_result=None, should_stop_after_turn=None))
        if self.settings.delegation.enabled and self.runtime_factory is None:
            raise ValueError('evidence delegation requires an explicit prepared-runtime host')
        async with AsyncExitStack() as stack:
            runtime = None
            if self.runtime_factory is not None:
                runtime = await stack.enter_async_context(self.runtime_factory(config=role_config,
                    workspace=workspace, services=services, tools=tuple(tools),
                    system_prompt=system+'\n'+mission, prepare_config=prepare_config))
                role_config = runtime.config
                tools = list(role_config.tools)
            messages = [UserMessage(initial_content or self.settings.instructions.initial)]
            while True:
                services.check()
                result=await AgentRunner(role_config, runtime=runtime).run(messages,
                    tools=tools,system_prompt=role_config.system_prompt if runtime is not None else system+'\n'+mission,signal=services.signal,observe=services.observe,record=services.record)
                services.check()
                if result.is_error:
                    raise RuntimeError('Agent runtime failed: '+str(result.error_details))
                if submitted is not None:return submitted
                if submission_result is not None:
                    value = submission_result()
                    if value is not None:
                        return value
                answers=[m for m in result.messages if isinstance(m,AssistantMessage)]
                if not answers or answers[-1].stop_reason!='stop' or answers[-1].tool_calls:
                    raise RuntimeError('Agent did not finish its role invocation')
                response = answers[-1].text
                if validate_final is None:
                    return response
                try:
                    validate_final(response)
                    return response
                except (ValueError, TypeError, KeyError) as exc:
                    services.record('role-submission-rejected', detail=str(exc))
                    messages = [*result.messages, UserMessage(
                        self.settings.instructions.repair.replace('{error}', str(exc)[:4000]))]
