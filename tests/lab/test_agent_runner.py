"""Role invocations share Core behavior and isolate histories and tools."""
import unittest
from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.data_model import UserMessage,AgentToolResult,TextBlock
from fruitfly_agent.core.tool_runtime import AgentTool
from fruitfly_agent.lab.agents import AgentRunner
from tests.support.faux_provider import FauxProvider


class AgentRunnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_many_requests_keep_tools_available_and_record_actual_usage(self):
        provider=FauxProvider()
        for _ in range(55):provider.respond_tool_call('inspect',{})
        provider.respond_text('done')
        async def inspect(ctx):return AgentToolResult(content=[TextBlock('observed')])
        calls=[];events=[]
        tool=AgentTool(name='inspect',label='Inspect',description='Read',parameters={'type':'object','properties':{}},execute=inspect)
        result=await AgentRunner(AgentLoopConfig(provider=provider,max_turns=1,max_tool_calls_per_turn=1)).run(
            [UserMessage('Work')],tools=(tool,),observe=lambda kind:calls.append(kind),record=lambda e,**f:events.append((e,f)))
        self.assertFalse(result.is_error)
        self.assertEqual(result.tool_call_count,55)
        self.assertEqual(len(calls),56)
        self.assertTrue(all(c['tools']==['inspect']for c in provider.calls))
        self.assertEqual(sum(e=='response'for e,_ in events),56)

    async def test_reused_runner_does_not_reuse_role_history_or_ambient_tools(self):
        provider=FauxProvider();provider.respond_text('first');provider.respond_text('second')
        runner=AgentRunner(AgentLoopConfig(provider=provider))
        await runner.run([UserMessage('First role')],system_prompt='editor')
        await runner.run([UserMessage('Second role')],system_prompt='evaluator')
        self.assertEqual(len(provider.calls[1]['messages']),1)
        self.assertEqual(provider.calls[1]['system_prompt'],'evaluator')
        self.assertEqual(provider.calls[1]['tools'],[])
