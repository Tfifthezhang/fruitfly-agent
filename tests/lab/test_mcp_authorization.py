"""Per-tool grants are transient and do not inherit ordinary execution approval."""
import unittest
from fruitfly_agent.core.tool_runtime.authorization import AuthorizationPrompt, AuthorizationRequest, ToolPermission
from fruitfly_agent.interactive.interaction.authorization import AuthorizationService
from fruitfly_agent.lab.mcp.authorization import ExternalToolPolicy


class McpAuthorizationTests(unittest.IsolatedAsyncioTestCase):
    async def test_session_grant_is_bound_to_tool_and_frozen_service_identity(self):
        service = AuthorizationService()
        self.addAsyncCleanup(service.close)
        prompts = []
        async def confirm(prompt):
            prompts.append(prompt)
            return 'session'
        service.handler = confirm
        await service.confirm(AuthorizationPrompt('1', 'bash', 'execute', (), 'test', 'execution'))
        request = AuthorizationRequest('2', 'mcp_first', {'value': None}, ToolPermission('external_tool'))
        first = ExternalToolPolicy('fixture', 'echo', {'digest': 'a'})
        for _ in range(2):
            async with first.authorize(request, service.confirm) as decision:
                self.assertTrue(decision.allowed)
        self.assertEqual(2, len(prompts))
        changed = ExternalToolPolicy('fixture', 'echo', {'digest': 'b'})
        async with changed.authorize(request, service.confirm) as decision:
            self.assertTrue(decision.allowed)
        second = AuthorizationRequest('3', 'mcp_second', {}, ToolPermission('external_tool'))
        async with first.authorize(second, service.confirm) as decision:
            self.assertTrue(decision.allowed)
        self.assertEqual(4, len(prompts))
        service.clear()
        service.handler = None
        async with first.authorize(request, service.confirm) as decision:
            self.assertFalse(decision.allowed)
