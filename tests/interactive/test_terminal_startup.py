"""Startup panel decisions and shared offline configuration editing."""
import asyncio
import io
import signal
import unittest
from unittest.mock import Mock

from fruitfly_agent.interactive import TerminalConfigurationFrontend
from fruitfly_agent.interactive.contracts.startup import StartupSnapshot
from fruitfly_agent.interactive.terminal.features.startup import TerminalStartupFrontend
from fruitfly_agent.interactive.terminal.io.menu import LineMenuInput, MenuAction, MenuEvent
from tests.support.configuration import MockConfiguration
from tests.support.terminal import MenuScriptedLines


class StartupPanelTests(unittest.TestCase):
    def panel(self, *lines):
        output = io.StringIO()
        return TerminalStartupFrontend(output_stream=output,
            menu_input=LineMenuInput(MenuScriptedLines(output, *lines))), output

    def test_complete_configuration_requires_an_explicit_start_or_exit_choice(self):
        snapshot = StartupSnapshot('fixture-model', 'Remote · fixture:22', 'New session', True)
        for value, action in (('1', 'start'), ('2', 'configure'), ('3', 'exit'), ('q', 'exit')):
            with self.subTest(value=value):
                panel, output = self.panel(value)
                self.assertEqual(panel.run(snapshot), action)
                self.assertIn('Connection not checked', output.getvalue())
                self.assertIn('Remote · fixture:22', output.getvalue())

    def test_incomplete_configuration_focuses_editor_and_cannot_start(self):
        panel, output = self.panel('1', '')
        self.assertEqual(panel.run(StartupSnapshot('Select a model', 'Local', 'New session', False,
            ('API key missing',))), 'configure')
        self.assertIn('Complete configuration first', output.getvalue())
        self.assertIn('API key missing', output.getvalue())

    def test_failure_notice_keeps_configuration_accessible(self):
        panel, output = self.panel('2')
        self.assertEqual(panel.run(StartupSnapshot('fixture', 'Remote', 'Resume · file', True),
            notice='Startup failed: connection unavailable'), 'configure')
        self.assertIn('Startup failed: connection unavailable', output.getvalue())

    def test_shared_editor_saves_without_returning_launch_intent(self):
        configuration = MockConfiguration(model='offline')
        output = io.StringIO()
        editor = TerminalConfigurationFrontend(configuration, output_stream=output,
            line_editor=MenuScriptedLines(output, '@Custom', 'space', 'back', 'back', '@Save and return'))
        result = editor.run_for_startup()
        self.assertTrue(result.saved)
        self.assertTrue(configuration.enabled)
        self.assertTrue(configuration.saved)
        self.assertNotIn('Save and start', output.getvalue())
        self.assertNotIn('Save and apply', output.getvalue())

    def test_shared_editor_retains_draft_after_save_failure_and_allows_retry(self):
        configuration = MockConfiguration(model='offline')
        save = configuration.save
        attempts = []
        def persist():
            attempts.append(configuration.changed)
            if len(attempts) == 1:
                raise OSError('fixture save failed')
            return save()
        configuration.save = Mock(side_effect=persist)
        output = io.StringIO()
        editor = TerminalConfigurationFrontend(configuration, output_stream=output,
            line_editor=MenuScriptedLines(output, '@Custom', 'space', 'back', 'back', '@Save and return',
                'back', '@Save and return'))
        self.assertTrue(editor.run_for_startup().saved)
        self.assertEqual(configuration.save.call_count, 2)
        self.assertEqual(attempts, [True, True])
        self.assertIn('Could not save configuration: fixture save failed', output.getvalue())

    def test_shared_editor_discards_changes_and_read_only_review_never_saves(self):
        for read_only in (False, True):
            with self.subTest(read_only=read_only):
                configuration = MockConfiguration(model='offline')
                configuration.read_only = read_only
                output = io.StringIO()
                lines = ('back',) if read_only else ('@Custom', 'space', 'back', 'back', '@Discard changes')
                editor = TerminalConfigurationFrontend(configuration, output_stream=output,
                    line_editor=MenuScriptedLines(output, *lines))
                self.assertFalse(editor.run_for_startup().saved)
                self.assertFalse(configuration.saved)
                self.assertFalse(configuration.changed)


class StartupWaitTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancel_waits_for_owned_cleanup_and_restores_signal_handler(self):
        cleanup = asyncio.Event()
        started = asyncio.Event()
        async def start():
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(.02)
                cleanup.set()
        class CancelInput:
            def read_event(self):
                return MenuEvent(MenuAction.QUIT)
            def poll_event(self, timeout):
                return MenuEvent(MenuAction.QUIT)
        panel = TerminalStartupFrontend(output_stream=io.StringIO(), menu_input=CancelInput())
        task = asyncio.create_task(start())
        await started.wait()
        previous = signal.getsignal(signal.SIGINT)
        self.assertFalse(await panel.wait_for_start(task, environment='fixture'))
        self.assertTrue(cleanup.is_set())
        self.assertIs(signal.getsignal(signal.SIGINT), previous)

    async def test_start_failure_and_cleanup_failure_propagate_to_host(self):
        from fruitfly_agent.interactive.contracts.runtime import RuntimeCleanupError
        for error in (RuntimeError('startup failed'), RuntimeCleanupError('cleanup failed')):
            with self.subTest(error=error):
                async def start():
                    raise error
                panel = TerminalStartupFrontend(input_stream=io.StringIO(), output_stream=io.StringIO())
                with self.assertRaisesRegex(type(error), str(error)):
                    await panel.wait_for_start(asyncio.create_task(start()), environment='fixture')
