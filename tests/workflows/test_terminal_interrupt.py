"""Actual terminal keys and signals stop a quiet Provider without losing the app."""
import os
import time
import unittest
from tests.support.terminal_process import TerminalProcess

CODE = '''
import asyncio, sys, termios
from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.data_model import AssistantMessage
from fruitfly_agent.core.model_stream import AssistantMessageEventStream, StreamDone
from fruitfly_agent.interactive import AgentApplication, InteractiveSession, TerminalFrontend
from tests.support.application import _Factory
calls = 0
before = termios.tcgetattr(sys.stdin)
def provider(view, *, signal=None):
    async def events():
        global calls
        calls += 1
        print('PROVIDER-WAITING-' + str(calls), flush=True)
        await asyncio.Event().wait()
        yield StreamDone(AssistantMessage())
    return AssistantMessageEventStream(events())
async def main():
    session = InteractiveSession(AgentLoopConfig(provider=provider, model='offline'))
    app = AgentApplication(_Factory([session]))
    await app.start()
    try:
        result = await TerminalFrontend(app).run()
    finally:
        await app.close()
    print('CLEAN-EXIT=' + str(result), flush=True)
    after = termios.tcgetattr(sys.stdin)
    # macOS marks pending input for reprocessing after raw-mode restoration.
    before[3] &= ~termios.PENDIN
    after[3] &= ~termios.PENDIN
    print('TERMINAL-RESTORED=' + str(after == before), flush=True)
asyncio.run(main())
'''


@unittest.skipUnless(os.name == 'posix', 'requires POSIX terminal controls')
class TerminalInterruptWorkflowTests(unittest.TestCase):
    def start(self, term):
        process = TerminalProcess(CODE, term=term)
        self.addCleanup(process.close)
        process.read_until('you> ' if term == 'dumb' else '❯ ')
        return process

    def test_control_c_cancels_quiet_run_and_allows_a_new_turn_for_ansi_and_fallback(self):
        for term in ('xterm-256color', 'dumb'):
            with self.subTest(term=term):
                process = self.start(term)
                process.send(b'wait\r')
                process.read_until('PROVIDER-WAITING-1')
                process.send(b'\x03')
                process.read_until('[run cancelled;')
                process.send(b'/status\r')
                process.read_until('state: idle')
                process.send(b'again\r')
                process.read_until('PROVIDER-WAITING-2')
                process.send(b'\x03')
                # Explicit exit also cancels active work through the same owner.
                process.send(b'/exit\r')
                output = process.finish()
                self.assertIn('CLEAN-EXIT=0', output)
                self.assertIn('TERMINAL-RESTORED=True', output)
                self.assertEqual(2, output.count('[run cancelled;'))

    def test_idle_double_interrupt_exits_cleanly_and_restores_terminal(self):
        for term in ('xterm-256color', 'dumb'):
            with self.subTest(term=term):
                process = self.start(term)
                process.send(b'draft\x03')
                process.read_until('input cleared.')
                process.send(b'\x03')
                output = process.finish()
                self.assertIn('CLEAN-EXIT=0', output)
                self.assertIn('TERMINAL-RESTORED=True', output)
                self.assertNotIn('PROVIDER-WAITING', output)

    def test_actual_sigint_uses_same_cancel_path_in_ansi_and_fallback(self):
        for term in ('xterm-256color', 'dumb'):
            with self.subTest(term=term):
                process = self.start(term)
                process.send(b'wait\r')
                process.read_until('PROVIDER-WAITING-1')
                process.signal()
                process.read_until('[run cancelled;')
                process.send(b'/exit\r')
                self.assertIn('TERMINAL-RESTORED=True', process.finish())

PERMISSION_CODE = CODE.replace(
    "    session = InteractiveSession(AgentLoopConfig(provider=provider, model='offline'))\n    app = AgentApplication(_Factory([session]))",
    """    import tempfile
    from pathlib import Path
    from fruitfly_agent.core.data_model import AgentToolResult, TextBlock
    from fruitfly_agent.core.tool_runtime import AgentTool
    from fruitfly_agent.core.tool_runtime.authorization import ToolPermission
    from fruitfly_agent.lab.environment.permissions import PermissionPolicy, PermissionAuthorizer
    from fruitfly_agent.interactive.authorization import AuthorizationService
    from tests.support.faux_provider import FauxProvider
    effects = []
    def execute(ctx):
        effects.append('effect')
        return AgentToolResult(content=[TextBlock('completed')])
    tool = AgentTool('fixture', 'fixture', 'fixture', {'type':'object', 'properties':{}, 'additionalProperties':False}, execute, permission=ToolPermission('execute'))
    scripted = FauxProvider()
    for result_text in ('DONE-ONE', 'DONE-TWO'):
        scripted.respond_tool_call('fixture', {})
        scripted.respond_text(result_text)
    service = AuthorizationService()
    authorizer = PermissionAuthorizer(PermissionPolicy(Path.cwd()), confirm=service.confirm)
    session = InteractiveSession(AgentLoopConfig(provider=scripted, model='offline', tools=(tool,), tool_authorizer=authorizer))
    service.emit = session.emit_frontend_event
    class Factory(_Factory):
        async def open(self, **kwargs):
            handle = await super().open(**kwargs)
            handle.authorization = service
            handle.components = {'authorization': service}
            return handle
    app = AgentApplication(Factory([session]))""",
).replace("    print('CLEAN-EXIT='", "    print('EFFECT-COUNT=' + str(len(effects)), flush=True)\n    print('CLEAN-EXIT='")

@unittest.skipUnless(os.name == 'posix', 'requires POSIX terminal controls')
class TerminalAuthorizationWorkflowTests(unittest.TestCase):
    def start(self, term):
        process = TerminalProcess(PERMISSION_CODE, term=term)
        self.addCleanup(process.close)
        process.read_until('you> ' if term == 'dumb' else '❯ ')
        process.send(b'first\r')
        process.read_until('3. Deny (Esc)')
        return process

    def test_enter_allows_once_and_the_next_call_requires_confirmation(self):
        for term in ('xterm-256color', 'dumb'):
            with self.subTest(term=term):
                process = self.start(term)
                process.send(b'\r')
                process.read_until('DONE-ONE')
                process.send(b'second\r')
                process.read_until('permission: once')
                # The second approval is a distinct request; inspect the appended transcript.
                deadline = time.monotonic() + 3
                while process.output.count(b'3. Deny (Esc)') < 2:
                    self.assertLess(time.monotonic(), deadline)
                    process._read()
                process.send(b'3' + (b'\r' if term == 'dumb' else b''))
                process.read_until('DONE-TWO')
                process.send(b'/exit\r')
                output = process.finish()
                self.assertIn('EFFECT-COUNT=1', output)
                self.assertIn('TERMINAL-RESTORED=True', output)

    def test_arrows_or_number_select_session_and_do_not_prompt_again(self):
        for term in ('xterm-256color', 'dumb'):
            with self.subTest(term=term):
                process = self.start(term)
                process.send(b'\x1b[B\r' if term != 'dumb' else b'2\r')
                process.read_until('DONE-ONE')
                process.send(b'second\r')
                process.read_until('DONE-TWO')
                process.send(b'/exit\r')
                output = process.finish()
                self.assertEqual(1, output.count('3. Deny (Esc)'))
                self.assertIn('EFFECT-COUNT=2', output)

    def test_escape_denies_and_ctrl_c_cancels_without_effects(self):
        for key, marker in ((b'\x1b', 'DONE-ONE'), (b'\x03', '[run cancelled;')):
            with self.subTest(key=key):
                process = self.start('xterm-256color')
                process.send(key)
                process.read_until(marker)
                process.send(b'/exit\r')
                output = process.finish()
                self.assertIn('EFFECT-COUNT=0', output)
                self.assertIn('TERMINAL-RESTORED=True', output)
