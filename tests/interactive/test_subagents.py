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
        self.assertIn('unknown input', detail)
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
