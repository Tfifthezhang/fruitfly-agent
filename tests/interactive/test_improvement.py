"""One task-driven command, explicit cost approval, and no implicit adoption."""
import asyncio
from dataclasses import replace
import io
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fruitfly_agent.interactive import TerminalFrontend, EvaluationSnapshot, EvaluationBenchmarkOption, EvaluationVariantOption
from fruitfly_agent.interactive.contracts.improvement import ImprovementPreview, ImprovementTargetView
from fruitfly_agent.interactive.terminal.bindings import ImprovementClients
from fruitfly_agent.interactive.terminal.io.menu import LineMenuInput
from tests.support.application import offline_session
from tests.support.faux_provider import FauxProvider
from tests.support.terminal import MenuScriptedLines, TtyStringIO


TARGET = ('@Target ·', '@Base prompt')


class ImprovementFrontendTests(unittest.IsolatedAsyncioTestCase):
    def controller(self, *, available=True):
        return SimpleNamespace(improvement_available=True,
            improvement_snapshot=Mock(return_value=EvaluationSnapshot((EvaluationBenchmarkOption('bench', 'Benchmark',
                'original tasks', 'fixed', (EvaluationVariantOption('starter', 'Five tasks', '3 train / 1 selection / 1 confirmation',
                    available, () if available else ('Start Docker',)),)),))),
            benchmark_preview=Mock(return_value=ImprovementPreview('method', 'Improvement', 'Downloads tasks and makes paid model calls',
                (('Maximum model calls', '80'), ('Training cases', '3')), 'base_prompt', 'one-use')),
            improve=AsyncMock(return_value=()))

    async def run_frontend(self, controller, *lines, clients=None, tty=False):
        clients = replace(clients or ImprovementClients(), targets=lambda: (
            ImprovementTargetView('H', 'base_prompt', 'Base prompt'),))
        output = TtyStringIO() if tty else io.StringIO()
        provider = FauxProvider()
        frontend = TerminalFrontend(offline_session(provider=provider), evaluation=controller,
            improvement_clients=clients or ImprovementClients(),
            input_stream=TtyStringIO() if tty else io.StringIO(), output_stream=output,
            line_editor=MenuScriptedLines(output, *lines, None))
        if tty:
            frontend.menu_input = LineMenuInput(frontend.line_editor)
        self.assertEqual(await frontend.run(), 0)
        self.assertEqual(provider.calls, [])
        return frontend, output.getvalue()

    async def test_removed_commands_cannot_start_any_paid_work(self):
        controller = self.controller()
        _, output = await self.run_frontend(controller, '/eval', '/optimize', '/exit')
        self.assertIn('unknown command: /eval', output)
        self.assertIn('unknown command: /optimize', output)
        controller.benchmark_preview.assert_not_called()
        controller.improve.assert_not_awaited()

    async def test_missing_workflow_reason_survives_benchmark_menu_exit(self):
        controller = self.controller()
        controller.improvement_available = False
        search = SimpleNamespace(improvement_preview=Mock(return_value=ImprovementPreview(
            'method','Method','Costs',target='base_prompt')), start_improvement=Mock())
        with patch.dict('os.environ', {'TERM': 'xterm-256color'}):
            _, output = await self.run_frontend(controller, '/improvement', *TARGET, '@Task ·', '@Benchmark tasks', 'q', '/exit',
                clients=ImprovementClients(search=search), tty=True)
        self.assertIn('Benchmark tasks', output)
        self.assertIn('\x1b[?1049h', output)
        transcript = output.rsplit('\x1b[?1049l', 1)[1]
        self.assertIn('no executable search and verification binding', transcript)
        controller.improvement_snapshot.assert_not_called()
        controller.benchmark_preview.assert_not_called()
        controller.improve.assert_not_awaited()
        search.start_improvement.assert_not_called()

    async def test_benchmark_errors_remain_visible_after_restoring_chat(self):
        for stage, reason in (('catalog', 'catalog failed'), ('empty', 'No benchmark task sources'),
                              ('variants', 'No task sets'), ('preflight', 'Start Docker'),
                              ('preview', 'preview failed'), ('execution', 'execution failed')):
            with self.subTest(stage=stage):
                controller = self.controller(available=stage != 'preflight')
                choices = [*TARGET, '@Task ·']
                if stage == 'catalog':
                    controller.improvement_snapshot.side_effect = RuntimeError(reason)
                elif stage == 'empty':
                    controller.improvement_snapshot.return_value = EvaluationSnapshot(())
                elif stage == 'variants':
                    controller.improvement_snapshot.return_value = EvaluationSnapshot((
                        EvaluationBenchmarkOption('bench', 'Benchmark', 'tasks', 'fixed', ()),))
                    choices += ['@Benchmark']
                else:
                    choices += ['@Benchmark / Five tasks']
                    if stage == 'preview':
                        controller.benchmark_preview.side_effect = ValueError(reason)
                    elif stage == 'execution':
                        controller.improve.side_effect = RuntimeError(reason)
                        choices += ['@Start improvement','@Start improvement']
                with patch.dict('os.environ', {'TERM': 'xterm-256color'}):
                    _, output = await self.run_frontend(controller, '/improvement', *choices, 'q', '/exit', tty=True)
                transcript = output.rsplit('\x1b[?1049l', 1)[1]
                self.assertIn(reason, transcript)
                if stage != 'execution':
                    controller.improve.assert_not_awaited()

    async def test_benchmark_completion_and_cancellation_survive_menu_exit(self):
        for outcome in ('complete', 'cancel', 'cancelled-job'):
            with self.subTest(outcome=outcome):
                controller = self.controller()
                if outcome == 'cancelled-job':
                    controller.improve.side_effect = asyncio.CancelledError()
                with patch.dict('os.environ', {'TERM': 'xterm-256color'}):
                    _, output = await self.run_frontend(controller, '/improvement', *TARGET, '@Task ·','@Benchmark / Five tasks','@Start improvement',
                        '2' if outcome == 'cancel' else '1', 'q', '/exit', tty=True)
                transcript = output.rsplit('\x1b[?1049l', 1)[1]
                self.assertIn('Improvement completed' if outcome == 'complete' else 'Improvement cancelled', transcript)
                if outcome != 'cancel':
                    self.assertIn('Improvement · Result', output)

    async def test_benchmark_has_one_cost_confirmation_defaulting_to_cancel(self):
        for answer, started in (('', False), ('2', False), ('1', True)):
            with self.subTest(answer=answer):
                controller = self.controller()
                _, output = await self.run_frontend(controller, '/improvement improve task success',
                    *TARGET,'@Task ·','@Benchmark / Five tasks','@Start improvement',answer,'q','/exit')
                self.assertEqual(output.count('Confirm improvement'),1)
                self.assertIn('Maximum model calls: 80', output)
                self.assertIn('Training cases: 3', output)
                self.assertTrue(controller.benchmark_preview.called)
                self.assertEqual(controller.benchmark_preview.call_args.args[1], 'improve task success')
                self.assertEqual(controller.improve.await_count, int(started))
                if started:
                    self.assertEqual(controller.improve.call_args.args, ('one-use',))

    async def test_unavailable_task_environment_rejects_before_preview(self):
        controller = self.controller(available=False)
        _, output = await self.run_frontend(controller, '/improvement', *TARGET,'@Task ·','@Benchmark / Five tasks','q','/exit')
        self.assertIn('Start Docker', output)
        controller.benchmark_preview.assert_not_called()
        controller.improve.assert_not_awaited()

    async def test_task_packages_and_benchmarks_share_one_picker(self):
        controller = self.controller()
        search = SimpleNamespace(improvement_preview=Mock(return_value=ImprovementPreview(
            'method','Method','Costs',target='base_prompt')),start_improvement=Mock())
        _, output = await self.run_frontend(controller,'/improvement',*TARGET,'@Task ·','back','q','/exit',
            clients=ImprovementClients(search=search))
        self.assertIn('Saved tasks',output)
        self.assertIn('Configured task cases',output)
        self.assertIn('Benchmark / Five tasks',output)
        self.assertNotIn('Choose task source',output)
        search.start_improvement.assert_not_called()
        controller.improve.assert_not_awaited()

    async def test_cooperative_cancellation_returns_to_results(self):
        controller=self.controller()
        controller.improve.side_effect=asyncio.CancelledError()
        _,output=await self.run_frontend(controller,'/improvement',*TARGET,'@Task ·','@Benchmark / Five tasks','@Start improvement','1','q','/exit')
        self.assertIn('Improvement cancelled',output)
        self.assertIn('Improvement · Result · cancelled',output)

    async def test_benchmark_tool_output_is_complete_in_unified_panel(self):
        controller=self.controller()
        text='original task tool detail '*1000
        async def improve(token,on_event):
            await on_event({'type':'agent_event','event':{'type':'tool_output','run_id':'trial',
                'tool_call_id':'call','tool_name':'bash','text':text}})
            return ()
        controller.improve.side_effect=improve
        _,output=await self.run_frontend(controller,'/improvement',*TARGET,'@Task ·','@Benchmark / Five tasks','@Start improvement','1','q','/exit')
        self.assertIn(text,output)
        self.assertNotIn('live tool output truncated',output)
