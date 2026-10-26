"""Native terminal history survives resize while the live input reflows."""
import os
import unittest

from tests.support.terminal_process import TerminalProcess

CODE = '''
import asyncio
from fruitfly_agent.interactive import AgentApplication, TerminalFrontend
from tests.support.application import _Factory, offline_session
from tests.support.faux_provider import FauxProvider
async def main():
    provider = FauxProvider()
    provider.respond_text('| Path | Detail |\\n|---|---|\\n| complete-long-directory-name.jsonl | complete-description-for-this-record |')
    app = AgentApplication(_Factory([offline_session(provider=provider)]))
    await app.start()
    try:
        await TerminalFrontend(app).run()
    finally:
        await app.close()
    print('REQUEST-COUNT=' + str(len(provider.calls)), flush=True)
asyncio.run(main())
'''


@unittest.skipUnless(os.name == 'posix', 'requires POSIX terminal controls')
class TerminalReflowTest(unittest.TestCase):
    def test_resize_preserves_completed_table_once_and_unsent_draft(self):
        process = TerminalProcess(CODE)
        self.addCleanup(process.close)
        process.resize(20, 32)
        process.read_until('❯ ')
        process.send(b'show\r')
        process.read_until('10 in / 5 out]')
        process.send(b'unsent draft')
        process.read_until('unsent draft')
        offset = len(process.output)
        process.resize(20, 100)
        process.read_until('unsent draft', start=offset)
        # Ctrl+U clears only the unsent text. Resize must not submit it.
        process.send(b'\x15/exit\r')
        output = process.finish()
        self.assertIn('REQUEST-COUNT=1', output)
        # Completed content stays in native history; widening only redraws input.
        after_resize = process.output[offset:].decode(errors='replace')
        self.assertNotIn('complete-lon', after_resize)
        self.assertNotIn('complete-des', after_resize)
        self.assertNotIn('\x1b[?1049h', output)
        self.assertNotIn('\x1b[H', output)
        # Both cells wrap at the original narrow width, preserving every segment.
        for segment in ('complete-lon', 'g-directory-', 'name.jsonl',
                        'complete-des', 'cription-for', '-this-record'):
            self.assertIn(segment, output)
