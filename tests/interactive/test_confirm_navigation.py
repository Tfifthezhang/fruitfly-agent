"""Confirmation keys must update what the user sees before any action runs."""
import io
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

from fruitfly_agent.interactive import TerminalFrontend
from fruitfly_agent.interactive.optimization import OptimizationPreview
from fruitfly_agent.interactive.terminal.menu import (
    LineMenuInput, MenuRow, RawTerminalMenuInput, TerminalMenuRenderer,
)


class ConfirmationNavigationTests(unittest.IsolatedAsyncioTestCase):
    def frontend(self, events):
        output = io.StringIO()
        preview = OptimizationPreview('opro', 'OPRO', 'Model calls may incur cost.', target='base_prompt', preview_token='confirmed-token')
        session = SimpleNamespace(set_event_sink=Mock(), optimization_preview=Mock(return_value=preview), start_optimization=Mock())
        frontend = TerminalFrontend(session, input_stream=io.StringIO(), output_stream=output)
        sequence = iter(events)
        def read_event():
            # Moving or reading another key must never start the job.
            session.start_optimization.assert_not_called()
            return RawTerminalMenuInput.decode(next(sequence))
        frontend.menu_input = SimpleNamespace(read_event=read_event)
        frontend.menu_renderer = TerminalMenuRenderer(output)
        frontend.menu_renderer.ansi = True
        frontend.menu_renderer.color = False
        return frontend, session, output

    async def test_search_confirmation_arrows_redraw_before_enter(self):
        scenarios = (
            ((b'\x1b[A', b'\r'), [1, 0], True),
            ((b'\x1b[A', b'\x1b[B', b'\r'), [1, 0, 1], False),
            ((b'\r',), [1], False),
            ((b'\x1b[A', b'\x1b'), [1, 0], False),
        )
        for events, expected, start in scenarios:
            with self.subTest(events=events):
                frontend, session, output = self.frontend(events)
                await frontend._start_optimization_flow('improve')
                frames = [f for f in output.getvalue().split('\x1b[2J\x1b[H') if f.startswith('Confirm optimization')]
                selections = [0 if '> 1. Start search' in f else 1 for f in frames]
                self.assertEqual(expected, selections)
                self.assertTrue(all('> 1. Start search' in f or '> 2. Cancel' in f for f in frames))
                if start:
                    session.start_optimization.assert_called_once_with('improve', preview_token='confirmed-token')
                else:
                    session.start_optimization.assert_not_called()

    def test_shared_confirmation_pages_redraw_visible_selection(self):
        for title, label in (
            ('Confirm training task', 'Save task'),
            ('Training answer already exists', 'Replace answer'),
            ('Confirm candidate activation', 'Start a fresh session with this candidate'),
        ):
            with self.subTest(title=title):
                frontend, session, output = self.frontend((b'\x1b[A', b'\r'))
                self.assertTrue(frontend._confirm_choice(title=title, subtitle='Review first', rows=(MenuRow(label), MenuRow('Cancel'))))
                self.assertIn('> 2. Cancel', output.getvalue())
                self.assertIn(f'> 1. {label}', output.getvalue())
                session.start_optimization.assert_not_called()

    def test_numbered_confirmation_retains_default_cancel(self):
        for value, expected in (('1', True), ('2', False), ('', False), ('q', False)):
            with self.subTest(value=value):
                frontend, _, _ = self.frontend(())
                frontend.menu_renderer.ansi = False
                frontend.menu_input = LineMenuInput(SimpleNamespace(read_line=lambda: value))
                self.assertEqual(expected, frontend._confirm_choice(title='Confirm', subtitle='', rows=(MenuRow('Proceed'), MenuRow('Cancel'))))

    async def test_candidate_actions_preserve_arrow_selection_and_execute_on_enter(self):
        scenarios = (
            ((b'\x1b[A', b'\r'), [3, 2], 'reject'),
            ((b'\x1b[A', b'\x1b[A', b'\r'), [3, 2, 1], 'adopt'),
            ((b'\x1b[B', b'\r', b'\x1b[A', b'\r'), [3, 0], 'activate'),
            ((b'\r',), [3], None),
            ((b'\x1b[A', b'\x1b'), [3, 2], None),
            ((b'\x1b[A', b'\x1b[6~', b'\x1b[5~', b'\r'), [3, 2, 2, 2], 'reject'),
        )
        for events, expected, action in scenarios:
            with self.subTest(events=events):
                frontend, session, output = self.frontend(events)
                session.candidate_detail = Mock(return_value=(SimpleNamespace(
                    candidate_id='candidate-1', status='proposed', algorithm='OPRO',
                    target='base_prompt', evidence=()), '\n'.join(f'line {i}' for i in range(25))))
                session.candidate_action = Mock()
                session.adopt_candidate = AsyncMock()
                sequence = iter(events)
                def read_event():
                    session.candidate_action.assert_not_called()
                    session.adopt_candidate.assert_not_called()
                    return RawTerminalMenuInput.decode(next(sequence))
                frontend.menu_input = SimpleNamespace(read_event=read_event)
                await frontend._candidate_detail_flow('candidate-1')
                frames = [f for f in output.getvalue().split('\x1b[2J\x1b[H') if f.startswith('Candidate candidate-')]
                selections = [next(i for i in range(4) if f'> {i + 1}.' in frame) for frame in frames]
                self.assertEqual(expected, selections)
                if action == 'activate':
                    session.adopt_candidate.assert_awaited_once_with('candidate-1')
                    session.candidate_action.assert_not_called()
                elif action:
                    session.candidate_action.assert_called_once_with('candidate-1', action)
                    session.adopt_candidate.assert_not_awaited()
                else:
                    session.candidate_action.assert_not_called()
                    session.adopt_candidate.assert_not_awaited()

    async def test_candidate_with_fewer_actions_defaults_to_back_and_navigates(self):
        frontend, session, output = self.frontend((b'\x1b[A', b'\x1b'))
        session.candidate_detail = Mock(return_value=(SimpleNamespace(
            candidate_id='candidate-1', status='selected_for_next_session',
            algorithm='custom', target='base_prompt', evidence=()), 'change'))
        session.candidate_action = Mock()
        await frontend._candidate_detail_flow('candidate-1')
        self.assertIn('> 2. Back', output.getvalue())
        self.assertIn('> 1. Use for a new session', output.getvalue())
        session.candidate_action.assert_not_called()
