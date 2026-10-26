"""Custom tool validation participates in the existing dispatch and hook boundary."""
import unittest
from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.data_model import AgentToolResult, TextBlock, UserMessage
from fruitfly_agent.core.errors import Result
from fruitfly_agent.core.extensions.hooks import HookRegistry, BEFORE_TOOL
from fruitfly_agent.core.loop import run_agent_loop
from fruitfly_agent.core.tool_runtime import AgentTool
from tests.support.faux_provider import FauxProvider


class ToolValidationTests(unittest.IsolatedAsyncioTestCase):
    async def run_tool(self, validator, *, mutate=False):
        provider = FauxProvider()
        provider.respond_tool_call('fixture', {'value': None})
        provider.respond_text('done')
        calls = []
        tool = AgentTool('fixture', 'Fixture', 'Fixture', {'type': 'object', 'properties': {}},
            lambda ctx: calls.append(ctx.args) or AgentToolResult(content=[TextBlock('executed')]),
            validate_arguments=validator)
        hooks = HookRegistry()
        if mutate:
            def change(event):
                event.args['value'] = 'changed'
            hooks.add(BEFORE_TOOL, change)
        result = await run_agent_loop(AgentLoopConfig(provider, tools=(tool,), hooks=hooks), [UserMessage('test')])
        return calls, next(message for message in result.messages if message.role == 'toolResult')

    async def test_nulls_are_preserved_by_custom_validation(self):
        calls, result = await self.run_tool(lambda args: Result.success(args))
        self.assertEqual([{'value': None}], calls)
        self.assertFalse(result.is_error)

    async def test_modified_arguments_are_validated_again_before_execution(self):
        def validate(args):
            return Result.success(args) if args.get('value') is None else Result.failure('changed value rejected')
        calls, result = await self.run_tool(validate, mutate=True)
        self.assertEqual([], calls)
        self.assertTrue(result.is_error)
        self.assertIn('changed value rejected', result.text)

    async def test_broken_or_invalid_validator_does_not_execute(self):
        def broken(args):
            raise ValueError('fixture-private-value')
        for validator in (broken, lambda args: None, lambda args: Result.success([])):
            with self.subTest(validator=validator):
                calls, result = await self.run_tool(validator)
                self.assertEqual([], calls)
                self.assertTrue(result.is_error)
                self.assertNotIn('fixture-private-value', result.text)
