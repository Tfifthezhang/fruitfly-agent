"""Compose workspace access with a shared Agent invocation; roles own policy."""
from dataclasses import replace
from fruitfly_agent.core.data_model import AssistantMessage, UserMessage
from fruitfly_agent.lab.agents import AgentRunner
from .access import EvidenceAccess
from .tools import evidence_tools


class EvidenceSession:
    def __init__(self, config, artifacts, *, page_characters=12000, reader_factory=None):
        self.config, self.artifacts, self.page_characters=config,artifacts,page_characters
        self.reader_factory = reader_factory
        if type(page_characters) is not int or not 1<=page_characters<=24000:
            raise ValueError('evidence page size must be 1..24000 characters')

    async def session(self, mission, workspace, services, *, writable=False, system='', submit=None, initial_content=None):
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
        reader = self.reader_factory(workspace, page_characters=self.page_characters) if self.reader_factory else None
        tools=list(evidence_tools(workspace,page_characters=self.page_characters,reader=reader))
        if writable:
            from ..editor.tools import editing_tools
            tools.extend(editing_tools(workspace,submit=seal if submit is not None else None))
        role_config=replace(self.config,env=None,hooks=None,prepare_next_turn=None,before_tool_call=None,after_tool_call=None,
            on_partial=None,on_tool_result=None,should_stop_after_turn=None)
        result=await AgentRunner(role_config).run([UserMessage(initial_content or 'Use catalog to discover the granted workspace, then read relevant evidence.')],
            tools=tools,system_prompt=system+'\n'+mission,signal=services.signal,observe=services.observe,record=services.record)
        services.check()
        if submitted is not None:return submitted
        answers=[m for m in result.messages if isinstance(m,AssistantMessage)]
        if result.is_error:
            raise RuntimeError('Agent runtime failed: '+str(result.error_details))
        if not answers or answers[-1].stop_reason!='stop' or answers[-1].tool_calls:
            raise RuntimeError('Agent did not finish its role invocation')
        return answers[-1].text
