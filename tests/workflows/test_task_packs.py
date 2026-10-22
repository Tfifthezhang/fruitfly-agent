"""Explicit task corrections preserve conversation and model-call boundaries."""
from pathlib import Path
import tempfile
import unittest

from tests.support.task_packs import install
from fruitfly_agent.lab.improvement.tasks import load_pack
from tests.support.application import open_task_app


class TaskPackApplicationTests(unittest.IsolatedAsyncioTestCase):
    open_app = open_task_app

    async def test_correction_without_improver_preserves_canonical_and_model_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            path = install(root)
            app, _, provider = await self.open_app(root)
            provider.respond_text("wrong answer")
            await app.submit("say C")
            before = app._handle.session.canonical_items()
            calls = len(provider.calls)
            task = app.correction_tasks()[0]
            pack = app.task_packs()[0]
            saved = app.save_training_task(task.task_id, pack.pack_id, "say C", "C", expected_hash=pack.source_hash, reason="human correction")
            self.assertEqual(2, saved.train_count)
            self.assertEqual(before, app._handle.session.canonical_items())
            self.assertEqual(calls, len(provider.calls))
            row = load_pack(root, path).material["train"][-1]
            self.assertEqual(task.task_id, row["source"]["message_id"])
            self.assertEqual("human correction", row["reason"])
            self.assertEqual((("UNSEEN_INPUT", "SECRET_ANSWER"),), app.task_pack_holdout("project"))

    async def test_normal_tasks_do_not_collect_learning_material(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            app, _, provider = await self.open_app(root)
            provider.respond_text('Answer')
            result = await app.submit('Question')
            await app.close()
            self.assertFalse(result.is_error)
            self.assertEqual(len(provider.calls), 1)
            self.assertFalse((root / '.fruitfly/learning').exists())
            self.assertEqual(list(root.glob('.fruitfly/improvement/task-packs/*/pack.json')), [])
