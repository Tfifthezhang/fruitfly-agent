"""Task packages through real Application, terminal and native improvers, offline."""
import asyncio
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from fruitfly_agent.interactive import AgentApplication, TerminalFrontend
from fruitfly_agent.run.application import RunApplicationFactory
from tests.support.faux_provider import FauxProvider
from tests.support.materials import _write_models
from tests.support.improvers import QueueEditor
from tests.support.task_packs import install, package
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

    async def test_material_recording_is_configured_without_an_improver(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            app, factory, provider = await self.open_app(root, 'task-material-recording')
            provider.respond_text('Unverified answer')
            await app.submit('A self-contained question')
            records = list(root.glob('.fruitfly/learning/materials/*.json'))
            self.assertEqual(len(records), 1)
            record = json.loads(records[0].read_text())
            self.assertEqual(record['material']['status'], 'pending')
            self.assertEqual(record['material']['acceptance'], '')
            self.assertEqual(record['partition'], 'train')
            self.assertEqual(record['source']['manifest'], app.runtime_manifest['digest'])
            self.assertEqual(len(provider.calls), 1)
            self.assertEqual(app.candidates(), ())
            self.assertEqual(list(root.glob('.fruitfly/improvement/task-packs/*/pack.json')), [])




    async def test_session_material_recording_flushes_at_close(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            app, factory, provider = await self.open_app(root, 'task-material-recording')
            factory.configuration.set_parameter('task-material-recording', 'trigger', 'session')
            factory.configuration.save()
            await app.rebuild()
            provider.respond_text('Unverified answer')
            await app.submit('Question')
            self.assertEqual(list(root.glob('.fruitfly/learning/materials/*.json')), [])
            await app.close()
            records = list(root.glob('.fruitfly/learning/materials/*.json'))
            self.assertEqual(len(records), 1)
            self.assertEqual(json.loads(records[0].read_text())['material']['status'], 'pending')
            self.assertEqual(len(provider.calls), 1)

