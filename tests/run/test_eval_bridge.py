"""Optional benchmark task selection and subprocess execution stay offline."""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import asyncio
import sys
import json
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fruitfly_agent.interactive.contracts.evaluation import BenchmarkImprovementRequest
from fruitfly_agent.run.evaluation import RunEvaluationController
from fruitfly_agent.run.adapters.benchmark_trials import BenchmarkTrialClient


class EvalBridgeTests(unittest.IsolatedAsyncioTestCase):
    def controller(self, cwd, *, environment=None, available=True):
        application = SimpleNamespace(running=False, pending_count=0, improve=AsyncMock(return_value=()))
        preview = SimpleNamespace(preview_token='one-use')
        factory = SimpleNamespace(cwd=cwd, environment=environment or {},
            benchmark_improvement_available=available, benchmark_task_preview=Mock(return_value=preview))
        return RunEvaluationController(application, factory), application, factory

    async def test_preview_is_offline_and_execution_consumes_one_token(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, application, factory = self.controller(Path(directory))
            request = BenchmarkImprovementRequest('terminal-bench', 'starter')
            preview = controller.benchmark_preview(request, 'Improve task success')
            selection, executor, direction = factory.benchmark_task_preview.call_args.args
            self.assertEqual(selection, __import__('dataclasses').asdict(request))
            self.assertIsInstance(executor, BenchmarkTrialClient)
            application.improve.assert_not_awaited()
            events = AsyncMock()
            self.assertEqual(await controller.improve(preview.preview_token, on_event=events), ())
            self.assertIs(executor.on_event, events)
            application.improve.assert_awaited_once_with(direction, preview_token='one-use')
            with self.assertRaisesRegex(ValueError, 'consumed'):
                await controller.improve(preview.preview_token)
            self.assertEqual(controller.improvement_previews, {})

    def test_explicit_method_selection_is_forwarded_without_starting_work(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, application, factory = self.controller(Path(directory))
            controller.benchmark_preview(BenchmarkImprovementRequest('terminal-bench', 'starter',
                generator_id='alternative', component_ids=('base_prompt',), width=2))
            selection = factory.benchmark_task_preview.call_args.args[0]
            self.assertEqual(selection['generator_id'], 'alternative')
            self.assertEqual(selection['component_ids'], ('base_prompt',))
            self.assertEqual(selection['width'], 2)
            application.improve.assert_not_awaited()

    async def test_failed_execution_still_consumes_preview(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, application, _ = self.controller(Path(directory))
            application.improve.side_effect = RuntimeError('failure')
            preview = controller.benchmark_preview(BenchmarkImprovementRequest('terminal-bench', 'starter'))
            with self.assertRaisesRegex(RuntimeError, 'failure'):
                await controller.improve(preview.preview_token)
            with self.assertRaisesRegex(ValueError, 'consumed'):
                await controller.improve(preview.preview_token)
            self.assertEqual(controller.improvement_previews, {})

    def test_unavailable_or_busy_application_rejects_before_preview(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, application, factory = self.controller(Path(directory), available=False)
            request = BenchmarkImprovementRequest('terminal-bench', 'starter')
            with self.assertRaisesRegex(ValueError, 'no executable search and verification binding'):
                controller.benchmark_preview(request)
            factory.benchmark_improvement_available = True
            for running, pending in ((True, 0), (False, 1)):
                application.running, application.pending_count = running, pending
                with self.assertRaisesRegex(RuntimeError, 'active work'):
                    controller.benchmark_preview(request)
            factory.benchmark_task_preview.assert_not_called()

    def test_controller_environment_includes_factory_loaded_values(self):
        controller, _, _ = self.controller(Path('/tmp'), environment={'FRUITFLY_TEST_SECRET': 'fake-value'})
        self.assertEqual(controller._environment()['FRUITFLY_TEST_SECRET'], 'fake-value')

    def test_catalog_works_outside_checkout_without_container_access(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, application, factory = self.controller(Path(directory))
            environment = controller._environment()
            environment['PATH'] = ''  # Preflight cannot reach an installed Docker.
            with patch.object(controller, '_environment', return_value=environment):
                snapshot = controller.improvement_snapshot()
            terminal = next(b for b in snapshot.benchmarks if b.benchmark_id == 'terminal-bench')
            starter = next(v for v in terminal.variants if v.variant_id == 'starter')
            self.assertIn('5 CPU tasks', starter.label)
            self.assertFalse(starter.available)
            self.assertTrue(starter.preflight)
            factory.benchmark_task_preview.assert_not_called()
            application.improve.assert_not_awaited()
            self.assertFalse((Path(directory) / '.fruitfly').exists())

    async def test_stderr_and_raw_stdout_are_visible_before_child_finishes(self):
        with tempfile.TemporaryDirectory() as directory:
            cwd = Path(directory)
            release = cwd / 'release'
            updates = []
            create_process = asyncio.create_subprocess_exec
            script = (
                "import sys,time,json; from pathlib import Path; "
                "print('raw stdout',flush=True); "
                "sys.stderr.buffer.write('Ｈｉ stderr'.encode()); sys.stderr.flush(); "
                f"p=Path({str(release)!r}); "
                "exec('while not p.exists():\\n time.sleep(0.01)'); "
                "print(json.dumps({'type':'task-set-prepared'}),flush=True)"
            )
            async def launch(*args, **kwargs):
                return await create_process(sys.executable, '-u', '-c', script, **kwargs)
            async def observe(event):
                updates.append(event)
                if event.get('source') == 'eval stderr':
                    release.touch()
            client = BenchmarkTrialClient(workspace=cwd, environment={}, on_event=observe)
            with patch('fruitfly_agent.run.adapters.benchmark_trials.asyncio.create_subprocess_exec', new=launch):
                result = await asyncio.wait_for(client._execute(('prepare',), root=cwd, timeout=2,
                    result_type='task-set-prepared'), timeout=5)
            self.assertEqual(result['type'], 'task-set-prepared')
            self.assertIn('raw stdout', ''.join(e.get('text', '') for e in updates))
            self.assertIn('Ｈｉ stderr', ''.join(e.get('text', '') for e in updates))

    async def test_observer_failure_does_not_abort_external_task(self):
        with tempfile.TemporaryDirectory() as directory:
            cwd = Path(directory)
            create_process = asyncio.create_subprocess_exec
            async def launch(*args, **kwargs):
                return await create_process(sys.executable, '-u', '-c',
                    "print('raw log'); print('{\"type\":\"task-set-prepared\"}')", **kwargs)
            client = BenchmarkTrialClient(workspace=cwd, environment={},
                on_event=AsyncMock(side_effect=RuntimeError('observer failed')))
            with patch('fruitfly_agent.run.adapters.benchmark_trials.asyncio.create_subprocess_exec', new=launch):
                result = await client._execute(('prepare',), root=cwd, timeout=2, result_type='task-set-prepared')
            self.assertEqual(result['type'], 'task-set-prepared')
            client.on_event.assert_awaited()

    def test_removed_evaluation_launch_api_is_not_exported(self):
        import fruitfly_agent.interactive as interactive
        import fruitfly_agent.interactive.contracts.evaluation as contracts
        for name in ('TerminalEvaluationFrontend', 'EvaluationController', 'EvaluationLaunchRequest',
                     'EvaluationLaunchResult', 'EvaluationImprovementController'):
            self.assertFalse(hasattr(interactive, name), name)
            self.assertFalse(hasattr(contracts, name), name)
        controller, _, factory = self.controller(Path('/tmp'))
        self.assertFalse(hasattr(controller, 'run'))
        self.assertFalse(hasattr(controller, 'improvement_preview'))
        from fruitfly_agent.run.application import RunApplicationFactory
        self.assertFalse(hasattr(RunApplicationFactory, 'benchmark_improvement_preview'))
