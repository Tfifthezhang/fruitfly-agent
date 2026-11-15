"""Read-only child monitoring and command registration use immutable views."""
from dataclasses import replace
import unittest
from fruitfly_agent.interactive.contracts.subagents import SubagentSnapshot, SubagentStatus
from fruitfly_agent.interactive.interaction.commands import parse_command
from fruitfly_agent.interactive.terminal.features.subagent import subagent_handler

class SubagentCommandTests(unittest.TestCase):
    def row(self):
        return SubagentStatus('agent', 'run', 'Inspect exports', 'running', 'pending', 'model', 'alias',
            'model', 1., 2., None, None, 1, 0, None, None, '', None, None)

    def test_disabled_empty_list_and_detail_do_not_start_work(self):
        self.assertIn('disabled', subagent_handler(lambda: None)(parse_command('/subagent')).text)
        class Monitor:
            rows = ()
            def snapshot(self): return SubagentSnapshot(3, 2, self.rows)
            def detail(self, agent_id, run_id=None):
                if agent_id != 'agent': raise ValueError('unknown')
                return self.rows[0]
        monitor = Monitor()
        handler = subagent_handler(lambda: monitor)
        self.assertIn('No subagents', handler(parse_command('/subagent')).text)
        monitor.rows = (self.row(),)
        self.assertIn('running', handler(parse_command('/subagent')).text)
        detail = handler(parse_command('/subagent agent run')).text
        self.assertIn('Input tokens', detail)
        self.assertIn('unknown', detail)
        self.assertIn('pending', detail)
        self.assertNotIn('%', detail)
        self.assertIn('Unknown', handler(parse_command('/subagent missing')).text)
        self.assertIn('usage:', handler(parse_command('/subagent a b c')).text)

    def test_result_text_cannot_inject_terminal_control_sequences(self):
        row = replace(self.row(), summary='\x1b[2Junsafe\x00', state='completed')
        class Monitor:
            def detail(self, *args): return row
        text = subagent_handler(lambda: Monitor())(parse_command('/subagent agent')).text
        self.assertNotIn('\x1b', text)
        self.assertNotIn('\x00', text)


    def test_snapshot_counts_all_records_and_keeps_latest_fifty_in_order(self):
        from fruitfly_agent.interactive.terminal.rendering.panels import render_command_panel
        from fruitfly_agent.interactive.terminal.io.text import cell_width
        rows = tuple(replace(self.row(), run_id=f'run-{i}', task='Ｗide task ' + 'x' * 170,
                             state='failed' if i == 0 else 'running') for i in range(51))
        calls = []
        class Monitor:
            def snapshot(self):
                calls.append('snapshot')
                return SubagentSnapshot(7, 2, rows)
        result = subagent_handler(lambda: Monitor())(parse_command('/subagent'))
        self.assertEqual(calls, ['snapshot'])
        sections = result.panel.sections
        self.assertEqual(dict(sections[0].rows), {
            'Agents': '1', 'Executions': '51', 'Shown': '50', 'Concurrency limit': '2', 'Revision': '7'})
        self.assertEqual(dict(sections[1].rows), {'failed': '1', 'running': '50'})
        self.assertEqual(dict(sections[2].rows)['Run ID'], 'run-1')
        self.assertEqual(dict(sections[-1].rows)['Run ID'], 'run-50')
        self.assertTrue(dict(sections[2].rows)['Task'].endswith('…'))
        self.assertIn('Counts cover all retained', result.text)
        for width in (12, 36, 80):
            text = render_command_panel(result.panel, columns=width)
            self.assertTrue(all(cell_width(line) < width for line in text.splitlines()))
        self.assertEqual(result.text, render_command_panel(result.panel))

    def test_empty_poisoned_snapshot_keeps_warning_and_zero_counts(self):
        class Monitor:
            def snapshot(self): return SubagentSnapshot(1, 2, (), poisoned=True)
        result = subagent_handler(lambda: Monitor())(parse_command('/subagent'))
        self.assertEqual(dict(result.panel.sections[0].rows)['Executions'], '0')
        self.assertIn('further execution is blocked', result.text)
        self.assertIn('No subagents', result.text)

    def test_detail_retains_error_and_summary_and_reads_only_detail(self):
        calls = []
        row = replace(self.row(), error='failure detail', summary='retained summary')
        class Monitor:
            def detail(self, *args):
                calls.append(args)
                return row
        result = subagent_handler(lambda: Monitor())(parse_command('/subagent agent run'))
        self.assertEqual(calls, [('agent', 'run')])
        self.assertEqual([section.title for section in result.panel.sections],
                         ['Task', 'Status', 'Recorded usage', 'Result'])
        self.assertIn('failure detail', result.text)
        self.assertIn('retained summary', result.text)

    def test_command_is_discovered_by_help_and_completion_without_input_loop_branches(self):
        import io
        from fruitfly_agent.interactive.terminal import TerminalFrontend
        from fruitfly_agent.interactive.terminal.commands import complete_command
        from tests.support.application import offline_session
        frontend = TerminalFrontend(offline_session(), input_stream=io.StringIO(), output_stream=io.StringIO())
        descriptions = frontend.command_descriptions()
        self.assertIn('subagent', {d.name for d in descriptions})
        from fruitfly_agent.interactive.terminal.io.completion import CompletionQuery
        result = complete_command(CompletionQuery('/suba', 5), descriptions)
        self.assertIn('/subagent', [item.replacement for item in result.items])
