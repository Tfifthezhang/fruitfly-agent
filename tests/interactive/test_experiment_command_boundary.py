"""Experiment execution is unavailable through daily chat commands."""
import io
import unittest
from fruitfly_agent.interactive import TerminalFrontend
from tests.support.application import offline_session
from tests.support.faux_provider import FauxProvider
from tests.support.terminal import MenuScriptedLines


class ImprovementFrontendTests(unittest.IsolatedAsyncioTestCase):


    def test_interactive_exports_no_benchmark_capability(self):
        import inspect
        import fruitfly_agent.interactive as interactive
        import fruitfly_agent.run as run
        self.assertNotIn('evaluation', inspect.signature(TerminalFrontend).parameters)
        for name in ('EvaluationSnapshot', 'EvaluationBenchmarkOption', 'EvaluationVariantOption'):
            self.assertFalse(hasattr(interactive, name))
        self.assertFalse(hasattr(run, 'RunEvaluationController'))

    async def test_removed_commands_never_start_paid_work(self):
        provider = FauxProvider()
        output = io.StringIO()
        frontend = TerminalFrontend(offline_session(provider=provider), input_stream=io.StringIO(), output_stream=output,
            line_editor=MenuScriptedLines(output, '/eval', '/optimize', '/improvement', '/candidate', '/candidates', '/help', '/exit'))
        await frontend.run()
        self.assertIn('unknown command: /eval', output.getvalue())
        self.assertIn('unknown command: /optimize', output.getvalue())
        for command in ('improvement', 'candidate', 'candidates'):
            self.assertIn('unknown command: /' + command, output.getvalue())
        self.assertNotIn('/improvement [TEXT]', output.getvalue())
        self.assertEqual(provider.calls, [])
