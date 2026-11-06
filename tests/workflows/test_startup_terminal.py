"""Real terminal cancellation restores the startup panel and terminal modes."""
import os
import unittest

from tests.support.terminal_process import TerminalProcess


CODE = '''
import asyncio, sys, termios, tempfile
from pathlib import Path
from unittest.mock import Mock, patch
from fruitfly_agent.run import cli
from fruitfly_agent.run.application import RunApplicationFactory
from fruitfly_agent.lab.environment.methods.remote import SshEnv
from fruitfly_agent.interactive.terminal.features.tool_services.approval import approve_start
from fruitfly_agent.interactive.contracts.tool_services import ToolServiceStartPlan
from tests.support.faux_provider import FauxProvider
from tests.support.run import _args, _write_catalog
before = termios.tcgetattr(sys.stdin)
async def waiting(backend):
    print('START-WAITING', flush=True)
    try:
        await asyncio.Event().wait()
    finally:
        print('START-CANCELLED', flush=True)
async def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        _write_catalog(root / '.fruitfly/models.yaml', {'offline': 'offline'})
        registry = Mock()
        provider = FauxProvider()
        registry.create.return_value = provider
        factory = RunApplicationFactory(cwd=root, provider_registry=registry,
            tool_service_startup_approval=approve_start,
            environment={'TEST_API_KEY': 'fixture', 'FRUITFLY_SSH_USERNAME': 'fixture',
                         'FRUITFLY_SSH_PASSWORD': 'fixture'})
        factory.configuration.set_mechanism('working-memory-reduction', enabled=False)
        factory.configuration.set_mechanism('remote-env', enabled=True)
        factory.configuration.set_parameter('remote-env', 'host', 'unavailable.example')
        factory.configuration.save()
        factory.reload_configuration()
        with patch.object(cli, 'RunApplicationFactory', return_value=factory), patch.object(SshEnv, 'start', waiting):
            result = await cli.run_cli(_args(cwd=directory))
        print('CLEAN-EXIT=' + str(result), flush=True)
        print('MODEL-CALLS=' + str(len(provider.calls)), flush=True)
asyncio.run(main())
after = termios.tcgetattr(sys.stdin)
before[3] &= ~getattr(termios, 'PENDIN', 0)
after[3] &= ~getattr(termios, 'PENDIN', 0)
print('TERMINAL-RESTORED=' + str(before == after), flush=True)
'''


@unittest.skipUnless(os.name == 'posix', 'requires POSIX terminal controls')
class StartupTerminalTests(unittest.TestCase):
    def test_control_c_and_sigint_return_to_panel_for_ansi_and_numbered_input(self):
        for term in ('xterm-256color', 'dumb'):
            for actual_signal in (False, True):
                with self.subTest(term=term, actual_signal=actual_signal), TerminalProcess(CODE, term=term) as process:
                    process.read_until('Start session')
                    process.send(b'\r')
                    process.read_until('START-WAITING')
                    if actual_signal:
                        process.signal()
                    else:
                        process.send(b'\x03')
                    process.read_until('Startup cancelled')
                    process.send(b'q' if term != 'dumb' else b'q\r')
                    output = process.finish()
                    self.assertIn('START-CANCELLED', output)
                    self.assertIn('CLEAN-EXIT=0', output)
                    self.assertIn('MODEL-CALLS=0', output)
                    self.assertIn('TERMINAL-RESTORED=True', output)
                    if term != 'dumb':
                        self.assertIn('\x1b[?1049l', output)

    def test_external_service_approval_exclusively_owns_startup_input(self):
        code = CODE.replace("    print('START-WAITING', flush=True)",
            "    allowed = await factory_for_approval.tool_service_startup_approval(\n"
            "        ToolServiceStartPlan('fixture', 'fixture-command', (), '/tmp', ()))\n"
            "    print('APPROVAL-ACCEPTED=' + str(allowed), flush=True)\n"
            "    print('START-WAITING', flush=True)")
        code = code.replace("        factory.configuration.save()", "        global factory_for_approval\n"
            "        factory_for_approval = factory\n        factory.configuration.save()")
        for term in ('xterm-256color', 'dumb'):
            with self.subTest(term=term), TerminalProcess(code, term=term) as process:
                process.read_until('Start session')
                process.send(b'\r')
                process.read_until('Allow? [y/N]')
                process.send(b'y\r')
                process.read_until('APPROVAL-ACCEPTED=True')
                process.read_until('START-WAITING')
                process.send(b'\x03')
                process.read_until('Startup cancelled')
                process.send(b'q' if term != 'dumb' else b'q\r')
                self.assertIn('TERMINAL-RESTORED=True', process.finish())
