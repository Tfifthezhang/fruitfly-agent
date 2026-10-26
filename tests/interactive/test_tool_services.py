"""Generic service status and startup review without external server access."""
import asyncio
import io
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fruitfly_agent.interactive.contracts.commands import InteractiveCommand
from fruitfly_agent.interactive.contracts.models import InteractiveStatus, ToolServiceStatus, InteractiveExecutionEnvironment
from fruitfly_agent.interactive.contracts.tool_services import ToolServiceStartPlan
from fruitfly_agent.interactive.interaction.commands import CommandRouter
from fruitfly_agent.interactive.terminal.features.tool_services.approval import approve_start


class ToolServiceViewTests(unittest.IsolatedAsyncioTestCase):
    def plan(self):
        return ToolServiceStartPlan('fixture', '/usr/bin/service', ('--stdio',), '/local/service', ('SERVICE_KEY',))

    async def test_redirected_startup_is_denied_without_reading_input(self):
        with patch('sys.stdin', io.StringIO('yes\n')), patch('sys.stdout', io.StringIO()) as output:
            self.assertFalse(await approve_start(self.plan()))
        self.assertEqual('', output.getvalue())

    async def test_review_shows_names_and_cancellation_joins_its_input_reader(self):
        entered, exited = threading.Event(), threading.Event()
        class Editor:
            def __init__(self, source, output, interrupted):
                self.interrupted = interrupted
            def read_line(self):
                entered.set()
                self.interrupted.wait(2)
                exited.set()
                return None
        source = io.StringIO()
        source.isatty = lambda: True
        with patch('sys.stdin', source), patch('sys.stdout', io.StringIO()) as output, patch(
                'fruitfly_agent.interactive.terminal.features.tool_services.approval.PollingLineEditor', Editor):
            pending = asyncio.create_task(approve_start(self.plan()))
            await asyncio.to_thread(entered.wait, 1)
            pending.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await pending
        self.assertTrue(exited.is_set())
        self.assertIn('SERVICE_KEY', output.getvalue())
        self.assertIn('Local host', output.getvalue())

    def test_lab_keeps_local_service_separate_from_remote_execution(self):
        status = InteractiveStatus('offline', '/local/workspace', 'session', 0, (), (),
            execution_environment=InteractiveExecutionEnvironment('SSH', '/remote/workspace', 'remote.example'),
            tool_services=(ToolServiceStatus('fixture', 'stdio', '/local/service', 'ready', ('echo',)),))
        result = CommandRouter().execute(InteractiveCommand('lab'), SimpleNamespace(status=status))
        self.assertIn('Local workspace: /local/workspace', result.text)
        self.assertIn('Local host', result.text)
        self.assertIn('/local/service', result.text)
        self.assertIn('echo', result.text)
        self.assertIn('/remote/workspace', result.text)
        self.assertIn('remote.example', result.text)
