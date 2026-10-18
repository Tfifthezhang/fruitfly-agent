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

    async def test_opro_uses_selected_package_without_configured_cases(self):
        for algorithm in ("opro",):
            with self.subTest(algorithm=algorithm), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp).resolve()
                install(root)
                app, factory, provider = await self.open_app(root, algorithm)
                manifest = app.runtime_manifest
                for text in ('wrong', 'wrong', '["Improved target"]', 'A', 'B', '["Improved target"]'):
                    provider.respond_text(text)
                preview = app.improvement_preview(pack_id="project", direction="improve")
                self.assertTrue(preview.preview_token)
                self.assertEqual(manifest, app.runtime_manifest)
                result = await app.improve("improve", preview_token=preview.preview_token)
                self.assertTrue(result)
                evidence = dict(result[0].evidence)
                snapshot = root / evidence["Task snapshot"]
                self.assertNotIn("SECRET_ANSWER", snapshot.read_text())
                self.assertNotIn("UNSEEN_INPUT", repr(provider.calls))
                self.assertNotIn("METADATA_ONLY", repr(provider.calls))
                self.assertEqual("project", evidence["Task package"])
                saved = factory.candidate_store.read(result[0].candidate_id)
                self.assertEqual(('project', 'Project regression'), (saved.task_pack_id, saved.task_pack_name))
                outputs = tuple((root / '.fruitfly/improvement/task-results/project').rglob('latest.txt'))
                self.assertEqual(1, len(outputs))
                self.assertEqual(factory.artifact_store.read_text(saved.artifact_id), outputs[0].read_text())
                receipt = json.loads(outputs[0].with_name('latest.json').read_text())
                self.assertEqual(saved.artifact_id, receipt['artifact_id'])
                self.assertEqual('project', receipt['task_pack_id'])
                snapshot_view = factory.configuration.snapshot()
                labels = dict(snapshot_view.prompt_option_labels)
                self.assertIn('Project regression', labels[saved.artifact_id])
                self.assertIn(algorithm.upper(), labels[saved.artifact_id])

                with self.assertRaisesRegex(ValueError, "consumed"):
                    await app.improve("improve", preview_token=preview.preview_token)
                await app.close()

    async def test_changed_package_or_request_requires_repreview_before_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            path = install(root)
            app, _, provider = await self.open_app(root, "opro")
            preview = app.improvement_preview(pack_id="project", direction="improve")
            payload = package()
            payload["train"][0]["expected"] = "modified"
            install(root, payload)
            with self.assertRaisesRegex(ValueError, "package changed"):
                await app.improve("improve", preview_token=preview.preview_token)
            self.assertEqual([], provider.calls)
            preview = app.improvement_preview(pack_id="project", direction="improve")
            with self.assertRaisesRegex(ValueError, "request changed"):
                await app.improve("different direction", preview_token=preview.preview_token)
            self.assertEqual([], provider.calls)

    async def test_mid_search_changes_only_affect_next_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            path = install(root)
            app, factory, provider = await self.open_app(root, "opro")
            preview = app.improvement_preview(pack_id="project", direction="improve")
            improver = factory._current_improver
            original = improver.search
            async def change_after_start(*args, **kwargs):
                payload = package()
                payload["train"][0]["expected"] = "future answer"
                install(root, payload)
                return await original(*args, **kwargs)
            improver.search = change_after_start
            for text in ('wrong', 'wrong', '["Improved target"]', 'A', 'B', '["Improved target"]'):
                provider.respond_text(text)
            results = await app.improve("improve", preview_token=preview.preview_token)
            self.assertTrue(results)
            self.assertNotIn("future answer", repr(provider.calls))
            next_preview = app.improvement_preview(pack_id="project", direction="improve")
            self.assertNotEqual(dict(preview.details)["Task package hash"], dict(next_preview.details)["Task package hash"])

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
            self.assertIsNone(factory._current_improver.host)
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

    async def test_terminal_selection_and_snapshot_confirm_before_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            install(root)
            app, _, provider = await self.open_app(root, "opro")
            editor = QueueEditor()
            # The absent conventional legacy file is optional; only the managed pack is offered.
            editor.send('/improvement improve', '@Target ·', '@Base prompt', '@OPRO', '@Task ·',
                '@Project regression', '@Start improvement', '@Cancel', 'q', '/exit')
            output = io.StringIO()
            editor.output = output
            await TerminalFrontend(app, input_stream=io.StringIO(), output_stream=output, line_editor=editor).run()
            self.assertIn("Saved tasks", output.getvalue())
            self.assertIn("Project regression", output.getvalue())
            self.assertNotIn("Configured task cases", output.getvalue())
            self.assertNotIn("cases file is unavailable", output.getvalue())
            self.assertIn("Confirm improvement", output.getvalue())
            self.assertEqual([], provider.calls)
            self.assertEqual((), app.candidates())

    async def test_saved_correction_is_reloaded_and_evaluated_by_next_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            install(root)
            app, factory, provider = await self.open_app(root)
            provider.respond_text("wrong answer")
            await app.submit("say C")
            task = app.correction_tasks()[0]
            pack = app.task_packs()[0]
            app.save_training_task(task.task_id, "project", "say C", "C", expected_hash=pack.source_hash)
            await app.close()
            factory.configuration.set_mechanism("opro", enabled=True)
            factory.configuration.save()
            factory.reload_configuration()
            restarted = AgentApplication(factory)
            await restarted.start()
            self.addAsyncCleanup(restarted.close)
            for text in ('wrong', 'wrong', 'wrong', '["Improved target"]', 'A', 'C', 'B', '["Improved target"]'):
                provider.respond_text(text)
            preview = restarted.improvement_preview(pack_id="project", direction="improve")
            self.assertEqual("2", dict(preview.details)["Training cases"])
            result = await restarted.improve("improve", preview_token=preview.preview_token)
            self.assertTrue(result)
            self.assertIn("say C", repr(provider.calls[1:]))
            snapshot = json.loads((root / dict(result[0].evidence)["Task snapshot"]).read_text())
            self.assertEqual("C", snapshot["task"]["train"][-1]["expected"])
            self.assertIn(task.task_id, repr(snapshot["task"]["case_sources"]))

    async def test_empty_validation_and_corrupt_snapshot_fail_without_model_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            payload = package()
            payload["validation"] = []
            install(root, payload)
            app, _, provider = await self.open_app(root, "opro")
            with self.assertRaisesRegex(ValueError, "independent validation"):
                app.improvement_preview(pack_id="project", direction="improve")
            install(root)
            preview = app.improvement_preview(pack_id="project", direction="improve")
            next(root.glob(".fruitfly/improvement/task-snapshots/*.json")).write_text("damaged")
            with self.assertRaisesRegex(ValueError, "corrupted"):
                await app.improve("improve", preview_token=preview.preview_token)
            self.assertEqual([], provider.calls)

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

    async def test_optional_material_service_does_not_block_other_host_search(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            install(root)
            app, _, provider = await self.open_app(root, "opro")
            source = app._handle.improvement
            names = ("improvement_preview", "improve", "cancel_improvement", "improvement_targets")
            app._handle.improvement = SimpleNamespace(**{name: getattr(source, name) for name in names})
            app._handle.task_packs = None
            self.assertFalse(app.task_packs_available)
            with self.assertRaisesRegex(RuntimeError, "service is unavailable"):
                app.task_packs()
            # Search-only hosts keep their own material handling and normal preview path.
            calls = []
            app._handle.improvement.improvement_preview = lambda *args, **kwargs: calls.append(kwargs) or source.improvement_preview(*args, pack_id="project", direction=kwargs["direction"])
            editor = QueueEditor()
            editor.send('/improvement improve', '@Target ·', '@Base prompt', '@Start improvement', '@Cancel', 'q', '/exit')
            output = io.StringIO()
            editor.output = output
            await TerminalFrontend(app, input_stream=io.StringIO(), output_stream=output, line_editor=editor).run()
            self.assertEqual(2, len(calls))  # Panel preview and fresh execution confirmation.
            self.assertNotIn("Choose task package", output.getvalue())
            self.assertEqual([], provider.calls)
