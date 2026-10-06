"""Native progress crosses the optional host contract and reaches terminal output."""
import asyncio
import io
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from fruitfly_agent.interactive import TerminalFrontend
from fruitfly_agent.interactive.commands import CommandRouter, parse_command
from fruitfly_agent.interactive.optimization import OptimizationActivity, OptimizationProgress
from fruitfly_agent.lab.optimization.services import NativeSearchServices
from tests.support import application as fixtures
from tests.support.task_packs import install


class OptimizationActivityTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_algorithm_exposes_live_and_final_progress(self):
        for algorithm in ('opro',):
            with self.subTest(algorithm=algorithm),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp).resolve();install(root)
                app,factory,provider=await fixtures.open_task_app(self,root,algorithm)
                entered=asyncio.Event();release=asyncio.Event()
                async def evaluator(text,case):
                    entered.set();await release.wait();return 1
                factory._current_optimizer.services_factory=lambda *a,**kw:NativeSearchServices(*a,**kw,evaluator=evaluator)
                provider.respond_text('["Improved target"]');provider.respond_text('["Improved target"]')
                preview=app.optimization_preview(pack_id='project',direction='improve')
                task=app.start_optimization('improve',preview_token=preview.preview_token)
                try:
                    await asyncio.wait_for(entered.wait(),1)
                    progress=app.optimization_progress
                    self.assertEqual('running',progress.status)
                    self.assertIsNotNone(progress.activity)
                    self.assertEqual((0,1,1),(progress.activity.completed,progress.activity.total,progress.activity.trial_calls))
                    text=CommandRouter().execute(parse_command('/status'),app).text
                    self.assertIn('optimization: running',text)
                    self.assertIn('0/1',text)
                    self.assertIn('trials used 1/',text)
                    self.assertNotIn('SECRET',text)
                    release.set();await task;await asyncio.sleep(0)
                    self.assertEqual('completed',app.optimization_progress.status)
                    self.assertGreater(app.optimization_progress.activity.model_calls,0)
                    self.assertGreater(app.optimization_progress.activity.trial_calls,0)
                    activity = app.optimization_progress.activity
                    self.assertEqual(activity.model_calls, activity.usage_reported_calls)
                    self.assertEqual(0, activity.usage_missing_calls)
                    self.assertGreater(activity.input_tokens + activity.output_tokens, 0)
                    status = CommandRouter().execute(parse_command('/status'), app).text
                    self.assertIn('reported tokens', status)
                    saved = factory.candidate_store.list()[0]
                    self.assertEqual(activity.input_tokens, saved.report['tokens']['input_tokens'])
                    self.assertEqual(activity.output_tokens, saved.report['tokens']['output_tokens'])

                finally:
                    release.set()
                    if not task.done():task.cancel()
                    await asyncio.gather(task,return_exceptions=True)
                    await app.close()

    async def test_inline_prompt_receives_logs_without_pressing_enter(self):
        started=threading.Event();release=threading.Event()
        def read_line():
            started.set();release.wait(3);return '/status'
        activity=OptimizationActivity('Evaluating training',2,8,3,64,2,32)
        session=SimpleNamespace(set_event_sink=Mock(),optimization_progress=OptimizationProgress(1,'running',activity=activity))
        output=io.StringIO()
        frontend=TerminalFrontend(session,input_stream=io.StringIO(),output_stream=output,line_editor=SimpleNamespace(read_line=read_line))
        # Exercise the polling branch; the real inline renderer has its own input lock tests.
        frontend._inline_display=object()
        task=asyncio.create_task(frontend._read_prompt_line())
        try:
            self.assertTrue(await asyncio.to_thread(started.wait,1))
            await asyncio.sleep(.6)
            self.assertFalse(task.done())
            self.assertIn('[optimization] Evaluating training [##--------] 2/8',output.getvalue())
            frontend._show_optimization_activity()
            self.assertEqual(1,output.getvalue().count('[optimization]'))
        finally:
            release.set()
            self.assertEqual('/status',await task)

    async def test_optional_broken_observer_does_not_stop_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();install(root)
            app,factory,provider=await fixtures.open_task_app(self,root,'opro')
            app._handle.optimization.optimization_activity=Mock(side_effect=RuntimeError('observer failure'))
            for text in ('wrong','wrong','["Improved target"]','A','B','["Improved target"]'):provider.respond_text(text)
            preview=app.optimization_preview(pack_id='project',direction='improve')
            result=await app.optimize('improve',preview_token=preview.preview_token)
            await asyncio.sleep(0)
            self.assertTrue(result)
            self.assertEqual('completed',app.optimization_progress.status)
            self.assertIsNone(app.optimization_progress.activity)
