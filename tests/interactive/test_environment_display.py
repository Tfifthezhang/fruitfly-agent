"""Execution and host paths stay distinct across all read-only presentations."""
from dataclasses import replace
from types import SimpleNamespace
import re
import unittest

from fruitfly_agent.interactive.contracts.models import InteractiveExecutionEnvironment, InteractiveStatus
from fruitfly_agent.interactive.contracts.commands import InteractiveCommand
from fruitfly_agent.interactive.interaction.commands import CommandRouter
from fruitfly_agent.interactive.terminal.rendering.panels import render_command_panel
from fruitfly_agent.interactive.terminal.rendering.welcome import render_welcome
from fruitfly_agent.interactive.terminal.io.text import cell_width


class EnvironmentDisplayTests(unittest.TestCase):
    def test_welcome_and_lab_preserve_complete_local_and_remote_locations_at_every_width(self):
        status = InteractiveStatus('offline', '/local/workspace/long-project-directory', '', 0, (), (),
            execution_environment=InteractiveExecutionEnvironment('Remote SSH',
                '/srv/remote/complete-project-directory', '[2001:db8::1]:2222'))
        result = CommandRouter().execute(InteractiveCommand('lab'), SimpleNamespace(status=status))
        for columns in (8, 18, 44, 80, 120):
            for color in (False, True):
                with self.subTest(columns=columns, color=color):
                    welcome = render_welcome(status, columns=columns, terminal_ui=True, color=color)
                    panel = render_command_panel(result.panel, columns=columns, color=color)
                    for rendered in (welcome, panel):
                        plain = re.sub(r'\x1b\[[0-9;]*m', '', rendered)
                        self.assertTrue(all(cell_width(line) <= columns - 1 for line in plain.splitlines()))
                        compact = ''.join(plain.split())
                        for value in (status.working_directory, status.execution_environment.working_directory,
                                      status.execution_environment.server, 'RemoteSSH'):
                            self.assertIn(value, compact)

    def test_local_unknown_and_custom_backends_do_not_invent_remote_or_local_targets(self):
        base = InteractiveStatus('offline', '/local/workspace', '', 0, (), ())
        for environment in (None, InteractiveExecutionEnvironment('Local', '/local/workspace'),
                            InteractiveExecutionEnvironment('Fixture backend', '/fixture/tasks', 'fixture-target')):
            with self.subTest(environment=environment):
                status = replace(base, execution_environment=environment)
                host = SimpleNamespace(status=status)
                outputs = (render_welcome(status, columns=80, terminal_ui=False, color=True),
                    CommandRouter().execute(InteractiveCommand('lab'), host).text,
                    CommandRouter().execute(InteractiveCommand('status'), host).text)
                for text in outputs:
                    self.assertNotIn('\x1b', text)
                    self.assertIn('/local/workspace', text)
                    self.assertIn(environment.label if environment else 'Unavailable', text)
                    self.assertNotIn('Connected', text)
                    if environment:
                        self.assertIn(environment.working_directory, text)
                        if environment.server:
                            self.assertIn(environment.server, text)
                    else:
                        self.assertNotIn('exec cwd:', text)
                        self.assertNotIn('execution directory:', text)
