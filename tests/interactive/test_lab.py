"""Runtime inspection stays read-only and separate from terminal presentation."""
from dataclasses import replace
import io
from pathlib import Path
import re
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from fruitfly_agent.interactive import AgentApplication, RuntimeHandle, TerminalFrontend
from fruitfly_agent.interactive.contracts.commands import (
    CommandPanel, CommandResult, CommandSection, InteractiveCommand,
)
from fruitfly_agent.interactive.contracts.models import InteractiveMechanism, InteractiveStatus
from fruitfly_agent.interactive.contracts.improvement import ComponentImprovementClient
from fruitfly_agent.interactive.interaction.commands import CommandRouter
from fruitfly_agent.interactive.terminal.io.text import cell_width
from fruitfly_agent.interactive.terminal.rendering.panels import render_command_panel
from fruitfly_agent.interactive.terminal.rendering.renderer import TerminalRenderer
from tests.support.application import offline_session
from tests.support.terminal import ScriptedLines, TtyStringIO


def status(**changes):
    return replace(InteractiveStatus('offline', '/workspace', 'session.jsonl', 0, (), ()), **changes)


def lab(value):
    return CommandRouter().execute(InteractiveCommand('lab'), SimpleNamespace(status=value))


class LabCommandTests(unittest.TestCase):
    def test_inspection_reads_one_snapshot_without_querying_services(self):
        snapshot = status(
            mechanisms=('context-fixture',),
            tool_names=('inspect_file', 'extra_tool'),
            mechanism_details=(
                InteractiveMechanism('context-fixture', 'context-manager', 'Fixture context', context_phase='augmentation'),
                InteractiveMechanism('remote-fixture', 'environment', 'Fixture execution backend'),
                InteractiveMechanism('tool-fixture', 'tools', 'Inspect a file', tool_names=('inspect_file', 'not_installed')),
                InteractiveMechanism('workflow-fixture', 'workflow', 'Execute stages'),
            ),
            improvement_available=True,
        )

        class Host:
            reads = 0
            @property
            def status(self):
                self.reads += 1
                return snapshot
            def __getattr__(self, name):
                raise AssertionError('inspection queried a service: ' + name)

        host = Host()
        result = CommandRouter().execute(InteractiveCommand('lab'), host)
        self.assertEqual(1, host.reads)
        self.assertIsNotNone(result.panel)
        self.assertEqual(['context-manager', 'environment', 'tools', 'workflow', 'improvement'],
                         [section.category for section in result.panel.sections])
        self.assertIn('Augmentation: Fixture context', result.text)
        self.assertIn('Externalization: Not enabled', result.text)
        self.assertIn('Fixture execution backend: Enabled', result.text)
        self.assertIn('inspect_file: Inspect a file', result.text)
        self.assertIn('extra_tool: Enabled', result.text)
        self.assertIn('Execute stages: Enabled', result.text)
        self.assertIn('Available · /improvement', result.text)
        self.assertNotIn('not_installed', result.text)
        self.assertNotIn('\x1b', result.text)
        self.assertEqual(('context-fixture',), snapshot.mechanisms)

    def test_unknown_categories_phases_and_legacy_ids_remain_visible(self):
        result = lab(status(
            mechanisms=('legacy-fixture',),
            mechanism_details=(
                InteractiveMechanism('missing-phase', 'context-manager', 'Unplaced context'),
                InteractiveMechanism('future-phase', 'context-manager', 'Future context', display_section='future'),
                InteractiveMechanism('extension', 'custom-research', 'Extension capability'),
            ),
        ))
        self.assertIn('Other: Unplaced context', result.text)
        self.assertIn('Future: Future context', result.text)
        self.assertIn('Custom Research\n  Extension capability: Enabled', result.text)
        self.assertIn('legacy-fixture: Enabled', result.text)

    def test_empty_and_unavailable_hosts_do_not_claim_improvement(self):
        result = lab(status())
        self.assertIn('Mechanisms: None enabled', result.text)
        self.assertNotIn('Available · /improvement', result.text)
        self.assertEqual('usage: /lab\n', CommandRouter().execute(
            InteractiveCommand('lab', ('unexpected',)), SimpleNamespace(),
        ).text)


class LabPresentationTests(unittest.IsolatedAsyncioTestCase):
    def panel(self):
        return lab(status(
            mechanism_details=(
                InteractiveMechanism('context-fixture', 'context-manager', 'Fixture context', display_section='reduction'),
                InteractiveMechanism('env-fixture', 'environment', 'Fixture environment'),
            ),
            tool_names=('inspect_file',),
        )).panel

    async def test_frontend_renders_panel_without_model_requests(self):
        session = offline_session(mechanism_details=(
            InteractiveMechanism('context-fixture', 'context-manager', 'Fixture context', display_section='reduction'),
        ))
        output = TtyStringIO()
        with patch.dict('os.environ', {'TERM': 'xterm-256color'}, clear=True):
            frontend = TerminalFrontend(session, input_stream=io.StringIO(), output_stream=output,
                                        line_editor=ScriptedLines('/lab', '/exit'))
            self.assertEqual(0, await frontend.run())
        rendered = output.getvalue()
        self.assertIn('\x1b[1;37;44m Context Manager \x1b[0m', rendered)
        self.assertIn('Fixture context', rendered)
        self.assertEqual(1, rendered.count('Lab · Active session'))
        self.assertEqual([], session.messages)
        self.assertEqual([], session.trace())

    def test_title_blocks_work_on_light_dark_and_unknown_palettes(self):
        for palette in ('0;15', '15;0', ''):
            with self.subTest(palette=palette), patch.dict('os.environ', {
                'TERM': 'xterm-256color', 'COLORFGBG': palette,
            }, clear=True):
                output = TtyStringIO()
                renderer = TerminalRenderer(output)
                renderer.write_command_result(CommandResult(panel=self.panel()))
                text = output.getvalue()
                self.assertIn('\x1b[1;37;44m Context Manager ', text)
                self.assertIn('\x1b[1;30;46m Environment ', text)
                self.assertIn('\x1b[1;37;45m Tools ', text)

    def test_no_color_dumb_and_redirected_output_keep_plain_sections(self):
        for output, environment in (
            (TtyStringIO(), {'TERM': 'xterm-256color', 'NO_COLOR': '1'}),
            (TtyStringIO(), {'TERM': 'dumb'}),
            (io.StringIO(), {'TERM': 'xterm-256color'}),
        ):
            with self.subTest(environment=environment), patch.dict('os.environ', environment, clear=True):
                renderer = TerminalRenderer(output)
                renderer.write_command_result(CommandResult(panel=self.panel()))
                self.assertIn('Context Manager\n', output.getvalue())
                self.assertIn('Not enabled', output.getvalue())
                self.assertNotIn('\x1b', output.getvalue())

    def test_narrow_panels_wrap_all_row_content_including_wide_characters(self):
        label = '路径名称很长/' + 'long-label-' * 4
        value = '/workspace/' + 'nested-directory/' * 6
        panel = CommandPanel('Runtime overview', (CommandSection('custom', 'Custom', ((label, value),)),))
        for columns in (4, 12, 36, 80):
            with self.subTest(columns=columns):
                text = render_command_panel(panel, columns=columns)
                width = max(4, columns - 1)
                self.assertTrue(all(cell_width(line) <= width for line in text.splitlines()))
                compact = ''.join(text.split())
                self.assertIn(label, compact)
                self.assertIn(value, compact)

    def test_unknown_categories_have_a_style_and_content_cannot_inject_controls(self):
        panel = CommandPanel('Title\x1b[2J', (CommandSection('extension', 'Custom\x1b[2J', (
            ('Name\x1b[2J', 'Value\x1b[2J'),
        )),))
        rendered = render_command_panel(panel, color=True)
        self.assertNotIn('\x1b[2J', rendered)
        self.assertIn('\\x1b[2J', rendered)
        self.assertIn('\x1b[1;37;44m', rendered)
        plain = re.sub(r'\x1b\[[0-9;]*m', '', rendered)
        self.assertNotIn('\x1b', plain)

    async def test_improvement_availability_follows_runtime_replacement_without_queries(self):
        service = Mock(spec=ComponentImprovementClient)
        legacy_service = Mock()
        services = iter((service, legacy_service, None))

        class Factory:
            configuration = None
            async def open(self, **kwargs):
                return RuntimeHandle(offline_session(), {}, improvement=next(services))
            def reload_configuration(self):
                pass
            def new_session_path(self):
                return Path('next-session.jsonl')

        app = AgentApplication(Factory())
        await app.start()
        try:
            self.assertTrue(app.status.improvement_available)
            self.assertIn('Available · /improvement', lab(app.status).text)
            self.assertEqual([], service.mock_calls)
            await app.rebuild()
            self.assertFalse(app.status.improvement_available)
            self.assertNotIn('Available · /improvement', lab(app.status).text)
            self.assertEqual([], legacy_service.mock_calls)
            await app.rebuild()
            self.assertFalse(app.status.improvement_available)
        finally:
            await app.close()
