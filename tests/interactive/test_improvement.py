"""One task-source menu and explicit confirmation for external execution."""
import io
import unittest
from fruitfly_agent.interactive import TerminalFrontend
from tests.support.application import offline_session
from tests.support.faux_provider import FauxProvider
from tests.support.terminal import MenuScriptedLines
from tests.support.improvement_ui import panel


class ImprovementFrontendTests(unittest.IsolatedAsyncioTestCase):
    async def test_task_sources_contain_only_generic_materials(self):
        view, client, frames, _ = panel((0, 1, 2, None), confirmed=True)
        await view.run()
        rows = next(rows for title, rows, _ in frames if title == 'Task material')
        self.assertEqual([row.label for row in rows], ['Current task and input files', 'Saved package'])
        request = client.workflow_preview.call_args.args[0]
        self.assertEqual(request.task_pack_id, 'pack')
        view.execute.assert_awaited_once_with(client.workflow_preview.return_value, '')

    async def test_confirmation_is_required_before_generic_execution(self):
        view, client, _, _ = panel((2, None), confirmed=False)
        await view.run()
        client.workflow_preview.assert_called_once()
        view.execute.assert_not_awaited()

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
            line_editor=MenuScriptedLines(output, '/eval', '/optimize', '/exit'))
        await frontend.run()
        self.assertIn('unknown command: /eval', output.getvalue())
        self.assertIn('unknown command: /optimize', output.getvalue())
        self.assertEqual(provider.calls, [])
