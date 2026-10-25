"""Registered commands, pure completion, and editing without execution effects."""
from contextlib import contextmanager
import io
import unittest
from unittest.mock import patch

from fruitfly_agent.interactive.contracts.commands import CommandDescription, CommandResult, InteractiveCommand, format_command_help
from fruitfly_agent.interactive.interaction.commands import CommandRouter, parse_command
from fruitfly_agent.interactive.terminal.commands import TerminalCommandRegistry, complete_command, effective_commands
from fruitfly_agent.interactive.terminal.io.completion import CompletionQuery, CompletionItem, CompletionResult, CompletionState, CompletionView
from fruitfly_agent.interactive.terminal.io.controls import ViewAction
from fruitfly_agent.interactive.terminal.io.live import InlineTerminalDisplay, IsolatedLineEditor
from fruitfly_agent.interactive.terminal import TerminalFrontend
from tests.support.application import offline_session
from tests.support.terminal import TtyStringIO, ScriptedLines

DESCRIPTIONS = (
    CommandDescription('improvement', 'Refine components', '/improvement [TEXT]'),
    CommandDescription('inspect', 'Inspect the runtime'),
    CommandDescription('status', 'Inspect status'),
)


class CompletionDataTests(unittest.TestCase):
    def test_filters_prefixes_case_and_aliases_and_hides_unavailable_commands(self):
        descriptions = CommandRouter().descriptions() + DESCRIPTIONS[:2]
        result = complete_command(CompletionQuery('/I', 2), descriptions)
        self.assertEqual(('/improvement', '/inspect'), tuple(i.replacement for i in result.items))
        self.assertEqual(('/quit',), tuple(i.replacement for i in complete_command(CompletionQuery('/qu', 3), descriptions).items))
        self.assertEqual('exit', parse_command('/quit').name)
        self.assertIsNone(complete_command(CompletionQuery('/res', 4), CommandRouter().descriptions()))
        self.assertIsNone(complete_command(CompletionQuery('/candidate', 10), CommandRouter().descriptions()))

    def test_paths_parameters_multiline_and_regular_text_do_not_trigger(self):
        for text, cursor in (('plain /im', 9), ('/Users/work/file', 15), ('/im/path', 8),
                             ('/im\\path', 8), ('/im text', 8), ('/im\nnext', 3), ('/im', 0)):
            with self.subTest(text=text):
                self.assertIsNone(complete_command(CompletionQuery(text, cursor), DESCRIPTIONS))

    def test_replacement_preserves_leading_space_arguments_and_cursor_position(self):
        state = CompletionState(lambda query: complete_command(query, DESCRIPTIONS))
        query = CompletionQuery('  /im  keep Ａrguments', 5)
        state.update(query)
        self.assertEqual('/improvement', state.view.items[0].replacement)
        accepted = state.accept(query)
        self.assertEqual(CompletionQuery('  /improvement  keep Ａrguments', 14), accepted)
        self.assertEqual(CompletionView(), state.view)
        state.update(accepted)
        self.assertFalse(state.view.items, 'accepted text stays dismissed until an edit')

    def test_dismissal_and_selected_item_survive_refresh_until_query_changes(self):
        state = CompletionState(lambda query: complete_command(query, DESCRIPTIONS))
        query = CompletionQuery('/i', 2)
        state.update(query)
        self.assertTrue(state.move(1))
        state.update(query)
        self.assertEqual('/inspect', state.view.items[state.view.selected].replacement)
        state.dismiss(query)
        state.update(query)
        self.assertFalse(state.view.items)
        state.update(CompletionQuery('/in', 3))
        self.assertEqual('/inspect', state.view.items[0].replacement)

    def test_accept_refreshes_registration_changes_and_rejects_invalid_ranges(self):
        options = [*DESCRIPTIONS]
        state = CompletionState(lambda query: complete_command(query, tuple(options)))
        query = CompletionQuery('/im', 3)
        state.update(query)
        options.clear()
        self.assertIsNone(state.accept(query))
        bad = CompletionState(lambda query: CompletionResult(-1, 8, (CompletionItem('x', '', 'x'),)))
        with self.assertRaisesRegex(ValueError, 'range'):
            bad.update(query)


class CommandDiscoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_help_and_candidates_follow_registration_replacement_and_hidden_overrides(self):
        calls = []
        router = CommandRouter({'base-extension': lambda command, context: CommandResult()})
        registry = TerminalCommandRegistry()
        registry.register('status', lambda command: calls.append(command) or CommandResult(text='override'),
            summary='Replacement status', usage='/status [DETAIL]')
        registry.register('inspect', lambda command: CommandResult(), summary='Inspect extension')
        registry.register('trace', lambda command: CommandResult(), discoverable=False)
        descriptions = effective_commands(router.descriptions(), registry.descriptions())
        text = format_command_help(descriptions)
        self.assertIn('/base-extension', text)
        self.assertIn('/status [DETAIL]', text)
        self.assertNotIn('show model, workspace', text)
        self.assertNotIn('/trace', text)
        self.assertEqual([], calls)
        self.assertIsNone(complete_command(CompletionQuery('/tr', 3), descriptions))
        self.assertEqual('override', (await registry.execute(InteractiveCommand('status'))).text)
        registry.register('inspect', lambda command: CommandResult(), replace=True, summary='New purpose')
        self.assertIn('New purpose', format_command_help(effective_commands(router.descriptions(), registry.descriptions())))

    async def test_terminal_help_includes_later_extensions_and_preserves_custom_help_handlers(self):
        output = io.StringIO()
        frontend = TerminalFrontend(offline_session(), output_stream=output,
            line_editor=ScriptedLines('/help', '/exit'))
        frontend.commands.register('inspect', lambda command: CommandResult(), summary='Inspect extension')
        await frontend.run()
        self.assertIn('/inspect', output.getvalue())
        self.assertIn('Inspect extension', output.getvalue())
        for custom in ('terminal', 'router'):
            output = io.StringIO()
            options = ({'command_handlers': {'help': lambda command: CommandResult(text='custom-help')}} if custom == 'terminal'
                else {'command_router': CommandRouter({'help': lambda command, context: CommandResult(text='custom-help')})})
            frontend = TerminalFrontend(offline_session(), output_stream=output,
                line_editor=ScriptedLines('/help', '/exit'), **options)
            await frontend.run()
            self.assertIn('custom-help', output.getvalue())

    def test_generic_help_uses_current_router_snapshot(self):
        router = CommandRouter()
        router.register('inspect', lambda command, context: CommandResult(), summary='Inspect extension')
        text = router.execute(InteractiveCommand('help'), offline_session()).text
        self.assertIn('/inspect', text)
        self.assertNotIn('/config', text)

    def test_exit_override_retains_the_existing_alias_once(self):
        router = CommandRouter()
        registry = TerminalCommandRegistry({'exit': lambda command: CommandResult(), 'quit': lambda command: CommandResult()})
        result = complete_command(CompletionQuery('/qu', 3), effective_commands(router.descriptions(), registry.descriptions()))
        self.assertEqual(['/quit'], [item.replacement for item in result.items])


class CompletionEditorTests(unittest.TestCase):
    @contextmanager
    def editor(self, keys, escapes=(), *, rows=20, columns=70):
        output = TtyStringIO()
        display = InlineTerminalDisplay(output, rows=rows, columns=columns, fullscreen=True)
        editor = IsolatedLineEditor(io.StringIO(), display)
        editor.set_completion_provider(lambda query: complete_command(query, DESCRIPTIONS))
        display.activate()
        try:
            with patch.object(editor.input, 'fileno', return_value=99), patch.object(editor, 'start'), patch.object(editor, 'stop'), patch(
                'fruitfly_agent.interactive.terminal.io.editor.select.select', return_value=([99], [], [])), patch(
                'fruitfly_agent.interactive.terminal.io.editor.os.read', side_effect=keys), patch(
                'fruitfly_agent.interactive.terminal.io.editor._read_escape_sequence', side_effect=escapes):
                yield editor, display, output
        finally:
            display.suspend()

    def test_tab_completes_without_submitting_and_enter_keeps_its_original_semantics(self):
        with self.editor([b'/', b'i', b'm', b'\t', b'\r']) as (editor, display, output):
            self.assertEqual('/improvement', editor.read_line())
            self.assertIn('Refine components', output.getvalue())
            self.assertFalse(display.transcript.records)
        with self.editor([b'/', b'i', b'm', b'\r']) as (editor, display, output):
            self.assertEqual('/im', editor.read_line())

    def test_arrows_select_candidates_and_escape_restores_input_history(self):
        with self.editor([b'/', b'i', b'\x1b', b'\t', b'\r'], [b'\x1b[B']) as (editor, display, output):
            self.assertEqual('/inspect', editor.read_line())
        with self.editor([b'/', b'i', b'\x1b', b'\x1b', b'\r'], [b'\x1b', b'\x1b[A']) as (editor, display, output):
            editor._history = ['previous prompt']
            self.assertEqual('previous prompt', editor.read_line())

    def test_bracketed_paste_preserves_tabs_and_newlines(self):
        with self.editor([b'\x1b', b'\r'], [b'\x1b[200~']) as (editor, display, output), patch(
                'fruitfly_agent.interactive.terminal.io.editor._read_bracketed_paste', return_value=b'/im\t\n/status'):
            self.assertEqual('/im\t\n/status', editor.read_line())

    def test_permission_input_has_priority_and_never_uses_completion(self):
        with self.editor([b'2']) as (editor, display, output):
            editor.set_choices(('Allow once', 'Allow session', 'Deny'), 'request')
            self.assertEqual('\x00authorize:request:2', editor.read_line())
            self.assertNotIn('Refine components', output.getvalue())

    def test_field_input_does_not_use_command_completion(self):
        with self.editor([b'/', b'i', b'm', b'\t', b'\r']) as (editor, display, output):
            editor._field_input = True
            self.assertEqual('/im', editor.read_line())
            self.assertNotIn('Refine components', output.getvalue())

    def test_copy_mode_clears_candidates_and_keeps_the_original_draft(self):
        with self.editor([b'/', b'i', b'm', b'\x1b', b'\x1b', b'\r'], [b'\x1bOQ', b'\x1b']) as (editor, display, output):
            self.assertEqual('/im', editor.read_line())
            self.assertIn('Copy:', output.getvalue())
            self.assertFalse(display.copying)

    def test_candidate_rows_are_bounded_scrolled_and_never_added_to_history(self):
        from fruitfly_agent.interactive.terminal.io.text import cell_width, truncate_cells
        items = tuple(CompletionItem('/item-' + str(i), 'A description Ａ', '/item-' + str(i)) for i in range(20))
        for rows in (6, 12, 24):
            for columns in (8, 20, 70):
                with self.subTest(rows=rows, columns=columns), patch.dict('os.environ', {'NO_COLOR': '1'}):
                    output = TtyStringIO()
                    display = InlineTerminalDisplay(output, rows=rows, columns=columns, fullscreen=True)
                    display.activate()
                    display.set_activity('working')
                    display.set_input('/it', 3)
                    display.set_completions(CompletionView(items, 17))
                    self.assertEqual(rows, len(display._rendered_rows))
                    self.assertTrue(all(cell_width(row) < columns for row in display._rendered_rows))
                    self.assertIn(truncate_cells('❯ /item-17  A description Ａ', columns - 1), display._rendered_rows)
                    self.assertFalse(display.transcript.records)
                    display.suspend()


class CompletionStreamingTests(unittest.IsolatedAsyncioTestCase):
    async def test_streamed_output_and_activity_preserve_candidates_and_the_draft(self):
        from fruitfly_agent.interactive.contracts.events import AssistantTextDelta
        from fruitfly_agent.interactive.terminal.rendering.renderer import TerminalRenderer
        output = TtyStringIO()
        with patch.dict('os.environ', {'TERM': 'xterm', 'NO_COLOR': '1'}):
            display = InlineTerminalDisplay(output, rows=16, columns=70, fullscreen=True)
            display.activate()
            renderer = TerminalRenderer(display)
            state = CompletionState(lambda query: complete_command(query, DESCRIPTIONS))
            query = CompletionQuery('/i', 2)
            state.update(query)
            state.move(1)
            display.set_input(query.text, query.cursor)
            display.set_completions(state.view)
            try:
                await renderer.render(AssistantTextDelta(run_id='run', text='New evidence while editing.'))
                display.set_activity('working')
                rows = '\n'.join(display._rendered_rows)
                self.assertIn('❯ /inspect', rows)
                self.assertIn('❯ /i', rows)
                self.assertEqual('/inspect', state.view.items[state.view.selected].replacement)
                self.assertNotIn('/inspect', display.transcript.records[0].source)
            finally:
                await renderer.close()
                display.suspend()
