"""One task-source menu and explicit confirmation for external execution."""
import io
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, AsyncMock
from fruitfly_agent.interactive import TerminalFrontend, EvaluationSnapshot, EvaluationBenchmarkOption, EvaluationVariantOption
from fruitfly_agent.interactive.contracts.improvement import ImprovementPreview
from fruitfly_agent.interactive.terminal.bindings import ImprovementClients
from tests.support.application import offline_session
from tests.support.faux_provider import FauxProvider
from tests.support.terminal import MenuScriptedLines
from tests.support.improvement_ui import configuration
from tests.support.improvement_ui import panel


class ImprovementFrontendTests(unittest.IsolatedAsyncioTestCase):
    def benchmark(self, available=True):
        return SimpleNamespace(improvement_available=True,
            improvement_snapshot=Mock(return_value=EvaluationSnapshot((EvaluationBenchmarkOption('bench', 'Benchmark',
                'Tasks', 'fixed', (EvaluationVariantOption('cpu', 'CPU tasks', 'Original task stream', available,
                    () if available else ('Start Docker',)),)),))),
            benchmark_preview=Mock(return_value=ImprovementPreview('rule', 'Rule', 'Paid requests', preview_token='external')),
            improve=AsyncMock(return_value=()))

    async def test_benchmark_task_selection_and_single_confirmation(self):
        for confirmed in (False, True):
            with self.subTest(confirmed=confirmed):
                benchmark = self.benchmark()
                view, client, _, _ = panel(
                    (0, 2, 0, 0, 9, None), text=('2',), confirmed=confirmed, benchmark=benchmark)
                await view.run()
                request, direction = benchmark.benchmark_preview.call_args.args
                self.assertEqual((request.benchmark_id, request.variant, request.task_limit), ('bench', 'cpu', 2))
                self.assertEqual(request.generator_id, 'rule')
                self.assertEqual(view.execute.await_count, int(confirmed))
                if confirmed:
                    self.assertEqual(view.execute.call_args.args[-1], 'benchmark')
                client.workflow_preview.assert_not_called()

    async def test_unavailable_environment_blocks_preview(self):
        benchmark = self.benchmark(False)
        view, _, _, notices = panel( (0, 2, 0, 0, None), benchmark=benchmark)
        await view.run()
        self.assertIn('Start Docker', ''.join(notices))
        benchmark.benchmark_preview.assert_not_called()
        view.execute.assert_not_awaited()

    async def test_catalog_error_preserves_saved_task_path(self):
        benchmark = self.benchmark()
        benchmark.improvement_snapshot.side_effect = RuntimeError('Catalog unavailable')
        view, _, _, notices = panel( (0, 2, 0, 1, None), benchmark=benchmark)
        await view.run()
        self.assertIn('Catalog unavailable', ''.join(notices))
        self.assertEqual(view.request.task_pack_id, 'pack')

    async def test_removed_commands_never_start_paid_work(self):
        provider = FauxProvider()
        output = io.StringIO()
        frontend = TerminalFrontend(offline_session(provider=provider), input_stream=io.StringIO(), output_stream=output,
            line_editor=MenuScriptedLines(output, '/eval', '/optimize', '/exit'))
        await frontend.run()
        self.assertIn('unknown command: /eval', output.getvalue())
        self.assertIn('unknown command: /optimize', output.getvalue())
        self.assertEqual(provider.calls, [])
