"""Real terminal key sequences exercise discovery, editing, and dispatch together."""
import os
import unittest


@unittest.skipUnless(os.name == 'posix', 'requires a POSIX PTY')
class CommandCompletionPtyTests(unittest.TestCase):
    def test_typing_shows_candidates_tab_only_edits_and_enter_executes_once(self):
        import fcntl
        import select
        import struct
        import subprocess
        import sys
        import termios
        import time
        master, slave = os.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 24, 80, 0, 0))
        original = termios.tcgetattr(slave)
        script = '''
import asyncio
from fruitfly_agent.interactive.terminal import TerminalFrontend
from fruitfly_agent.interactive.contracts.commands import CommandResult
from tests.support.application import offline_session
calls = []
def inspect(command):
    calls.append(command.name)
    return CommandResult(text='INSPECT_EXECUTED\\n')
frontend = TerminalFrontend(offline_session())
frontend.commands.register('inspect', inspect, summary='Inspect fixture')
asyncio.run(frontend.run())
print('CALLS:' + str(len(calls)), flush=True)
'''
        process = None
        received = bytearray()
        try:
            process = subprocess.Popen([sys.executable, '-c', script], stdin=slave, stdout=slave, stderr=slave,
                env={**os.environ, 'TERM': 'xterm', 'NO_COLOR': '1'})
            def until(marker):
                chunk = bytearray()
                deadline = time.monotonic() + 5
                while marker not in chunk:
                    remaining = deadline - time.monotonic()
                    self.assertGreater(remaining, 0, bytes(received + chunk).decode(errors='replace'))
                    if select.select([master], [], [], remaining)[0]:
                        chunk.extend(os.read(master, 65536))
                received.extend(chunk)
                return bytes(chunk)
            until('❯ '.encode())
            os.write(master, b'/')
            until(b'Tab complete')
            os.write(master, b'ins')
            until(b'Inspect fixture')
            self.assertNotIn(b'INSPECT_EXECUTED', received)
            os.write(master, b'\t')
            until('❯ /inspect'.encode())
            self.assertNotIn(b'INSPECT_EXECUTED', received)
            os.write(master, b'\r')
            until(b'INSPECT_EXECUTED')
            os.write(master, b'/he\t\r')
            help_output = until(b'Commands:')
            self.assertIn(b'/inspect', help_output)
            os.write(master, b'/exit\r')
            until(b'CALLS:1')
            self.assertEqual(0, process.wait(timeout=5))
            self.assertNotIn(b'\x1b[?1049h', received)
            self.assertNotIn(b'F2 copy', received)
            restored = termios.tcgetattr(slave)
            pending = getattr(termios, 'PENDIN', 0)
            original[3] &= ~pending
            restored[3] &= ~pending
            self.assertEqual(original, restored)
        finally:
            if process is not None and process.poll() is None:
                process.kill()
                process.wait()
            os.close(master)
            os.close(slave)
