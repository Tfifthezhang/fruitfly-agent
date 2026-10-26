"""Multi-turn chat stays in native scrollback across a temporary menu."""
import os
import unittest
from tests.support.terminal_process import TerminalProcess


CODE = '''
import asyncio
from fruitfly_agent.interactive import AgentApplication, TerminalFrontend
from fruitfly_agent.interactive.contracts.commands import CommandResult
from tests.support.application import _Factory, offline_session
from tests.support.faux_provider import FauxProvider
async def main():
    provider = FauxProvider()
    for prefix in ('first', 'second'):
        provider.respond_text('\\n\\n'.join(prefix + '-record-' + str(i).zfill(3) for i in range(60)))
    app = AgentApplication(_Factory([offline_session(provider=provider)]))
    await app.start()
    frontend = TerminalFrontend(app)
    def menu(command):
        with frontend.menu_scope():
            print('TEMPORARY-MENU', flush=True)
        return CommandResult(text='MENU-RETURNED\\n')
    frontend.commands.register('menu', menu, summary='Open fixture menu')
    try:
        await frontend.run()
    finally:
        await app.close()
    print('REQUEST-COUNT=' + str(len(provider.calls)), flush=True)
asyncio.run(main())
'''

STREAM_CODE = '''
import asyncio
from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.data_model import AssistantMessage, TextBlock
from fruitfly_agent.core.model_stream import AssistantMessageEventStream, TextDelta, StreamDone
from fruitfly_agent.interactive import AgentApplication, InteractiveSession, TerminalFrontend
from fruitfly_agent.interactive.contracts.commands import CommandResult
from fruitfly_agent.interactive.contracts.events import RunFinished
from tests.support.application import _Factory
async def main():
    menu_started, run_finished = asyncio.Event(), asyncio.Event()
    def provider(view, *, signal=None):
        async def events():
            yield TextDelta(text='BEFORE-MENU')
            await menu_started.wait()
            yield TextDelta(text='\\n\\nARRIVED-DURING-MENU')
            yield StreamDone(AssistantMessage(content=[TextBlock('BEFORE-MENU\\n\\nARRIVED-DURING-MENU')]))
        return AssistantMessageEventStream(events())
    session = InteractiveSession(AgentLoopConfig(provider=provider, model='offline'))
    app = AgentApplication(_Factory([session]))
    await app.start()
    frontend = TerminalFrontend(app)
    render = frontend.renderer.render
    async def observe(event):
        await render(event)
        if isinstance(event, RunFinished):
            run_finished.set()
    frontend.renderer.render = observe
    async def menu(command):
        with frontend.menu_scope():
            print('TEMPORARY-MENU', flush=True)
            menu_started.set()
            await asyncio.wait_for(run_finished.wait(), 3)
        return CommandResult(text='MENU-RETURNED\\n')
    frontend.commands.register('menu', menu, summary='Open fixture menu')
    try:
        await frontend.run()
    finally:
        await app.close()
asyncio.run(main())
'''


@unittest.skipUnless(os.name == 'posix', 'requires a POSIX terminal')
class TerminalScrollbackTests(unittest.TestCase):
    def test_stream_completion_during_async_menu_returns_to_native_history(self):
        process = TerminalProcess(STREAM_CODE)
        self.addCleanup(process.close)
        process.read_until('❯ ')
        process.send(b'run\r')
        process.read_until('BEFORE-MENU')
        process.send(b'/menu\r')
        process.read_until('MENU-RETURNED')
        process.send(b'/exit\r')
        output = process.finish()
        menu = output.split('\x1b[?1049h', 1)[1].split('\x1b[?1049l', 1)[0]
        after_menu = output.split('\x1b[?1049l', 1)[1]
        self.assertIn('TEMPORARY-MENU', menu)
        self.assertNotIn('ARRIVED-DURING-MENU', menu)
        self.assertIn('ARRIVED-DURING-MENU', after_menu)
        self.assertEqual(1, output.count('ARRIVED-DURING-MENU'))

    def test_long_answers_and_earlier_turns_survive_menu_and_exit(self):
        process = TerminalProcess(CODE)
        self.addCleanup(process.close)
        process.resize(14, 80)
        process.read_until('❯ ')
        process.send(b'first turn\r')
        process.read_until('10 in / 5 out]')
        before_menu = process.output.decode(errors='replace')
        self.assertNotIn('\x1b[?1049h', before_menu)
        for index in range(60):
            self.assertIn(f'first-record-{index:03d}', before_menu)
        process.send(b'/menu\r')
        process.read_until('MENU-RETURNED')
        offset = len(process.output)
        process.send(b'second turn\r')
        process.read_until('10 in / 5 out]', start=offset)
        process.send(b'/exit\r')
        output = process.finish()
        for prefix in ('first', 'second'):
            for index in range(60):
                self.assertIn(f'{prefix}-record-{index:03d}', output)
            # Old rows outside the preview are appended exactly once.
            self.assertEqual(1, output.count(prefix + '-record-000'))
        self.assertEqual(1, output.count('\x1b[?1049h'), 'only the temporary menu owns an alternate screen')
        self.assertEqual(1, output.count('\x1b[?1049l'))
        self.assertNotIn('first-record-', process.output[offset:].decode(errors='replace'))
        self.assertNotIn('\x1b[?1000h', output)
        self.assertNotIn('\x1b[?1006h', output)
        self.assertNotIn('F2 copy', output)
        self.assertIn('REQUEST-COUNT=2', output)
