"""Final tool arguments require explicit, fail-closed authorization."""
import asyncio
from contextlib import asynccontextmanager
import unittest

from fruitfly_agent.core.extensions.hooks import HookRegistry, BEFORE_TOOL
from fruitfly_agent.core.tool_runtime.authorization import AuthorizationDecision
from tests.support.faux_provider import FauxProvider
from tests.support.loop import make_tool, make_config, run_loop

class AuthorizationTests(unittest.IsolatedAsyncioTestCase):
    async def test_final_hook_arguments_are_authorized_and_authorizer_cannot_change_them(self):
        for mutate, allow in ((False, True), (True, True), (False, False)):
            with self.subTest(mutate=mutate, allow=allow):
                tool, calls = make_tool()
                observed = []
                class Authorizer:
                    @asynccontextmanager
                    async def authorize(self, request, *, signal=None):
                        observed.append(dict(request.arguments))
                        if mutate:
                            request.arguments['value'] = 'changed after authorization'
                        yield AuthorizationDecision(allow, 'denied by fixture')
                hooks = HookRegistry()
                def rewrite(event):
                    event.args['value'] = 'final'
                hooks.add(BEFORE_TOOL, rewrite)
                provider = FauxProvider()
                provider.respond_tool_call('count', {'value': 'original'})
                provider.respond_text('done')
                result = await run_loop(make_config(provider, [tool], hooks=hooks, tool_authorizer=Authorizer()), 'go')
                self.assertEqual([{'value': 'final'}], observed)
                self.assertEqual([{'value': 'final'}] if allow and not mutate else [], calls)
                self.assertEqual(not (allow and not mutate), result.messages[-2].is_error)

    async def test_exception_invalid_decision_and_missing_approval_do_not_execute(self):
        for failure in ('raise', 'invalid', 'deny'):
            with self.subTest(failure=failure):
                tool, calls = make_tool()
                class Authorizer:
                    @asynccontextmanager
                    async def authorize(self, request, *, signal=None):
                        if failure == 'raise':
                            raise RuntimeError('check failed')
                        yield None if failure == 'invalid' else AuthorizationDecision(False)
                provider = FauxProvider()
                provider.respond_tool_call('count', {'value': 'go'})
                provider.respond_text('done')
                result = await run_loop(make_config(provider, [tool], tool_authorizer=Authorizer()), 'go')
                self.assertEqual([], calls)
                self.assertTrue(result.messages[-2].is_error)

    async def test_cancellation_during_authorization_keeps_tool_unexecuted(self):
        entered = asyncio.Event()
        tool, calls = make_tool()
        class Authorizer:
            @asynccontextmanager
            async def authorize(self, request, *, signal=None):
                entered.set()
                await asyncio.Event().wait()
                yield AuthorizationDecision(True)
        provider = FauxProvider()
        provider.respond_tool_call('count', {'value': 'go'})
        task = asyncio.create_task(run_loop(make_config(provider, [tool], tool_authorizer=Authorizer()), 'go'))
        await entered.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual([], calls)
