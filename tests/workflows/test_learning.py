"""Application owns optional collection errors, cancellation and task boundaries."""
import asyncio
from types import SimpleNamespace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock

from tests.support.application import open_task_app


class LearningLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_recording_has_no_material_effects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app, factory, provider = await open_task_app(self, root)
            self.assertIsNone(app._handle.learning)
            provider.respond_text('answer')
            await app.submit('question')
            self.assertFalse((root / '.fruitfly/learning').exists())
            self.assertEqual(len(provider.calls), 1)

    async def test_collection_error_preserves_agent_result_and_is_visible(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, _, provider = await open_task_app(self, Path(tmp))
            app._handle.learning = SimpleNamespace(observe=AsyncMock(side_effect=RuntimeError('collection failed')))
            provider.respond_text('answer')
            result = await app.submit('question')
            self.assertFalse(result.is_error)
            self.assertIn('collection failed', str(app.last_error))
            self.assertEqual(app.state.value, 'idle')

    async def test_cancel_stops_collection_without_reversing_completed_answer(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, _, provider = await open_task_app(self, Path(tmp))
            started, closed = asyncio.Event(), asyncio.Event()
            async def observe(task):
                started.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    closed.set()
            app._handle.learning = SimpleNamespace(observe=observe)
            provider.respond_text('answer')
            submitted = asyncio.create_task(app.submit('question'))
            await asyncio.wait_for(started.wait(), 1)
            self.assertTrue(app.cancel())
            result = await asyncio.wait_for(submitted, 1)
            self.assertFalse(result.is_error)
            self.assertTrue(closed.is_set())
            self.assertEqual(app.state.value, 'idle')

    async def test_observations_do_not_repeat_previous_assistant_answers(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, _, provider = await open_task_app(self, Path(tmp))
            collector = SimpleNamespace(observe=AsyncMock(return_value=True))
            app._handle.learning = collector
            provider.respond_text('first answer')
            await app.submit('first question')
            provider.respond_text('second answer')
            await app.submit('second question')
            task = collector.observe.await_args.args[0]
            self.assertEqual(task.input, 'second question')
            self.assertEqual(task.output, 'second answer')
            self.assertNotIn('first answer', task.output)
