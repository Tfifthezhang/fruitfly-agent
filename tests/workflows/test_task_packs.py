"""Task packages through real Application, terminal and native optimizers, offline."""
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
from tests.support.optimizers import QueueEditor
from tests.support.task_packs import install, package
from fruitfly_agent.lab.optimization.task_packs import load_pack
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
                preview = app.optimization_preview(pack_id="project", direction="improve")
                self.assertTrue(preview.preview_token)
                self.assertEqual(manifest, app.runtime_manifest)
                result = await app.optimize("improve", preview_token=preview.preview_token)
                self.assertTrue(result)
                evidence = dict(result[0].evidence)
                snapshot = root / evidence["Task snapshot"]
                self.assertNotIn("SECRET_ANSWER", snapshot.read_text())
                self.assertNotIn("UNSEEN_INPUT", repr(provider.calls))
                self.assertNotIn("METADATA_ONLY", repr(provider.calls))
                self.assertEqual("project", evidence["Task package"])
                saved = factory.candidate_store.read(result[0].candidate_id)
                self.assertEqual(('project', 'Project regression'), (saved.task_pack_id, saved.task_pack_name))
                outputs = tuple((root / '.fruitfly/optimization/task-results/project').rglob('latest.txt'))
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
                    await app.optimize("improve", preview_token=preview.preview_token)
                await app.close()

    async def test_changed_package_or_request_requires_repreview_before_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            path = install(root)
            app, _, provider = await self.open_app(root, "opro")
            preview = app.optimization_preview(pack_id="project", direction="improve")
            payload = package()
            payload["train"][0]["expected"] = "modified"
            install(root, payload)
            with self.assertRaisesRegex(ValueError, "package changed"):
                await app.optimize("improve", preview_token=preview.preview_token)
            self.assertEqual([], provider.calls)
            preview = app.optimization_preview(pack_id="project", direction="improve")
            with self.assertRaisesRegex(ValueError, "request changed"):
                await app.optimize("different direction", preview_token=preview.preview_token)
            self.assertEqual([], provider.calls)

    async def test_mid_search_changes_only_affect_next_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            path = install(root)
            app, factory, provider = await self.open_app(root, "opro")
            preview = app.optimization_preview(pack_id="project", direction="improve")
            optimizer = factory._current_optimizer
            original = optimizer.search
            async def change_after_start(*args, **kwargs):
                payload = package()
                payload["train"][0]["expected"] = "future answer"
                install(root, payload)
                return await original(*args, **kwargs)
            optimizer.search = change_after_start
            for text in ('wrong', 'wrong', '["Improved target"]', 'A', 'B', '["Improved target"]'):
                provider.respond_text(text)
            results = await app.optimize("improve", preview_token=preview.preview_token)
            self.assertTrue(results)
            self.assertNotIn("future answer", repr(provider.calls))
            next_preview = app.optimization_preview(pack_id="project", direction="improve")
            self.assertNotEqual(dict(preview.details)["Task package hash"], dict(next_preview.details)["Task package hash"])

    async def test_correction_without_optimizer_preserves_canonical_and_model_calls(self):
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

    async def test_terminal_correction_save_cancel_and_create_package(self):
        for confirm in ("1", "2"):
            with self.subTest(confirm=confirm), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp).resolve()
                app, _, provider = await self.open_app(root)
                provider.respond_text("wrong")
                await app.submit("self-contained question")
                editor = QueueEditor()
                editor.send("/optimize", "3", "1", "1", "Corrections", "", "correct", "reason", confirm, "/exit")
                output = io.StringIO()
                await TerminalFrontend(app, input_stream=io.StringIO(), output_stream=output, line_editor=editor).run()
                files = tuple(root.glob(".fruitfly/optimization/task-packs/*/pack.json"))
                self.assertEqual(1 if confirm == "1" else 0, len(files))
                self.assertEqual(1, len(provider.calls))
                if confirm == "1":
                    payload = load_pack(root, files[0]).material
                    self.assertEqual("correct", payload["train"][0]["expected"])
                    self.assertEqual([], payload["validation"])
                    self.assertIn("Before searching", output.getvalue())

    async def test_terminal_selection_and_snapshot_confirm_before_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            install(root)
            app, _, provider = await self.open_app(root, "opro")
            editor = QueueEditor()
            # The absent conventional legacy file is optional; only the managed pack is offered.
            editor.send("/optimize improve", "1", "1", "2", "/exit")
            output = io.StringIO()
            await TerminalFrontend(app, input_stream=io.StringIO(), output_stream=output, line_editor=editor).run()
            self.assertIn("Choose task package", output.getvalue())
            self.assertIn("Project regression", output.getvalue())
            self.assertNotIn("Configured task cases", output.getvalue())
            self.assertNotIn("cases file is unavailable", output.getvalue())
            self.assertIn("Confirm optimization", output.getvalue())
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
            preview = restarted.optimization_preview(pack_id="project", direction="improve")
            self.assertEqual("2", dict(preview.details)["Training cases"])
            result = await restarted.optimize("improve", preview_token=preview.preview_token)
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
                app.optimization_preview(pack_id="project", direction="improve")
            install(root)
            preview = app.optimization_preview(pack_id="project", direction="improve")
            next(root.glob(".fruitfly/optimization/task-snapshots/*.json")).write_text("damaged")
            with self.assertRaisesRegex(ValueError, "corrupted"):
                await app.optimize("improve", preview_token=preview.preview_token)
            self.assertEqual([], provider.calls)

    async def test_ansi_correction_confirmation_uses_same_public_operations(self):
        from types import SimpleNamespace
        from fruitfly_agent.interactive.terminal.menu import RawTerminalMenuInput
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            app, _, provider = await self.open_app(root)
            provider.respond_text("wrong")
            await app.submit("question")
            editor = QueueEditor()
            editor.send("ANSI corrections", "", "answer", "")
            output = io.StringIO()
            frontend = TerminalFrontend(app, input_stream=io.StringIO(), output_stream=output, line_editor=editor)
            keys = iter((b"\r", b"\r", b"\x1b[A", b"\r"))
            frontend.menu_input = SimpleNamespace(read_event=lambda: RawTerminalMenuInput.decode(next(keys)))
            frontend.menu_renderer.ansi = True
            await frontend._save_correction_flow()
            files = list(root.glob(".fruitfly/optimization/task-packs/*/pack.json"))
            self.assertEqual(1, len(files))
            self.assertEqual("answer", load_pack(root, files[0]).material["train"][0]["expected"])
            self.assertEqual(1, len(provider.calls))

    async def test_optional_material_service_does_not_block_other_host_search(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            install(root)
            app, _, provider = await self.open_app(root, "opro")
            source = app._handle.optimization
            names = ("optimization_preview", "optimize", "cancel_optimization", "candidates", "candidate_notice",
                     "acknowledge_candidate_notice", "candidate_detail", "candidate_action")
            app._handle.optimization = SimpleNamespace(**{name: getattr(source, name) for name in names})
            self.assertFalse(app.task_packs_available)
            with self.assertRaisesRegex(RuntimeError, "service is unavailable"):
                app.task_packs()
            # Search-only hosts keep their own material handling and normal preview path.
            calls = []
            app._handle.optimization.optimization_preview = lambda *args, **kwargs: calls.append(kwargs) or source.optimization_preview(*args, pack_id="project", direction=kwargs["direction"])
            editor = QueueEditor()
            editor.send("/optimize improve", "1", "2", "/exit")
            output = io.StringIO()
            await TerminalFrontend(app, input_stream=io.StringIO(), output_stream=output, line_editor=editor).run()
            self.assertEqual(1, len(calls))
            self.assertNotIn("Choose task package", output.getvalue())
            self.assertEqual([], provider.calls)
