"""Actual Catalog/Application/terminal paths stop for review after independent gains."""
import asyncio
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from fruitfly_agent.interactive import AgentApplication, TerminalFrontend
from fruitfly_agent.lab.improvement.contracts.search import TaskCase
from fruitfly_agent.run.application import RunApplicationFactory
from tests.support.faux_provider import FauxProvider
from tests.support.materials import _write_models
from tests.support.improvers import QueueEditor
from tests.support.task_packs import install


class AutomaticImprovementWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def open_app(self, root, method="failure-replay", *, budget=64):
        _write_models(root)
        path = install(root)
        provider = FauxProvider()
        registry = Mock()
        registry.create.return_value = provider
        factory = RunApplicationFactory(cwd=root, environment={}, provider_registry=registry)
        factory.configuration.set_mechanism("opro", enabled=True)
        for key, value in {"rounds": 3, "batch_size": 2, "max_metric_calls": budget}.items():
            factory.configuration.set_parameter("opro", key, str(value))
        factory.configuration.set_mechanism(method, enabled=True)
        factory.configuration.set_mechanism("automatic-text-search", enabled=True)
        factory.configuration.save()
        factory.reload_configuration()
        app = AgentApplication(factory)
        await app.start()
        self.addAsyncCleanup(app.close)
        return app, factory, provider, path

    def script(self, provider, candidate, *, distill=False, confirmed=True):
        provider.respond_text("wrong")  # original selection baseline
        provider.respond_text("wrong")  # original training baseline
        if distill:
            source = TaskCase("say A", "A").case_id
            provider.respond_text(json.dumps({"tasks": [{"source_case_id": source,
                "input": "Learning exercise: respond with A", "acceptance": {"expected": "A"}}]}))
            provider.respond_text('{"accepted": true, "reason": "Matches the source requirement."}')
        provider.respond_text("wrong")  # learning baseline
        provider.respond_text(json.dumps([candidate, "unused candidate"]))
        provider.respond_text("A")  # learning candidate
        provider.respond_text("B")  # original selection candidate
        provider.respond_text("A")  # original training candidate
        provider.respond_text("wrong")  # independent baseline
        provider.respond_text("SECRET_ANSWER" if confirmed else "wrong")

    async def test_both_processors_use_same_review_and_activation_path(self):
        for method in ("failure-replay", "failure-distillation"):
            with self.subTest(method=method), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                app, factory, provider, path = await self.open_app(root, method)
                original_manifest = app.runtime_manifest
                original_files = {p.name: p.read_bytes() for p in path.parent.glob("*.json")}
                candidate = "Improved task guidance"
                self.script(provider, candidate, distill=method == "failure-distillation")
                preview = app.improvement_preview(pack_id="project", direction="Improve task success")
                records = await app.improve("Improve task success", preview_token=preview.preview_token)
                self.assertEqual(len(records), 1)
                self.assertEqual(app.runtime_manifest, original_manifest)
                self.assertEqual(factory.candidate_store.read(records[0].candidate_id).status, "proposed")
                view, diff = app.candidate_detail(records[0].candidate_id)
                evaluation = next(s.text for s in view.sections if s.title == "Evaluation")
                self.assertIn("Independent confirmation: passed", evaluation)
                self.assertIn("Independent score: 0.0 → 1.0", evaluation)
                self.assertIn(candidate, diff)
                for call in provider.calls:
                    if "Improve the declared text target" in call["system_prompt"] or "learning exercise" in call["system_prompt"]:
                        self.assertNotIn("UNSEEN_INPUT", repr(call))
                        self.assertNotIn("SECRET_ANSWER", repr(call))
                self.assertEqual(original_files, {p.name: p.read_bytes() for p in path.parent.glob("*.json")})
                self.assertEqual(factory.candidate_store.read(records[0].candidate_id).report["stop_reason"], "confirmed_improvement")
                adopted = await app.adopt_candidate(records[0].candidate_id)
                self.assertEqual(adopted.status, "adopted")
                self.assertNotEqual(app.runtime_manifest["digest"], original_manifest["digest"])
                provider.respond_text("Continued normally")
                await app.submit("Continue the task")
                self.assertIn(candidate, provider.calls[-1]["system_prompt"])
                await app.close()

    async def test_rejected_confirmation_keeps_runtime_and_candidate_inbox_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, factory, provider, _ = await self.open_app(Path(tmp))
            before = app.runtime_manifest
            self.script(provider, "candidate", confirmed=False)
            preview = app.improvement_preview(pack_id="project", direction="Improve")
            self.assertEqual(await app.improve("Improve", preview_token=preview.preview_token), ())
            self.assertEqual(app.runtime_manifest, before)
            self.assertEqual(app.candidates(), ())
            self.assertEqual(len(provider.calls), 9)
            self.assertEqual(app.improvement_progress.activity.phase,
                             "Automatic search stopped: confirmation failed")

    async def test_real_terminal_starts_one_bounded_job_then_waits_for_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, factory, provider, _ = await self.open_app(Path(tmp))
            before = app.runtime_manifest
            self.script(provider, "Improved guidance")
            editor = QueueEditor()
            output = io.StringIO()
            frontend = TerminalFrontend(app, input_stream=io.StringIO(), output_stream=output, line_editor=editor)
            editor.send("/improvement Improve", "1", "1", "1", "1", "1", "1")
            running = asyncio.create_task(frontend.run())
            try:
                for _ in range(200):
                    if app.improvement_progress.sequence:
                        break
                    await asyncio.sleep(.005)
                self.assertGreater(app.improvement_progress.sequence, 0)
                await app.wait_for_improvement()
                self.assertEqual(len(app.candidates()), 1)
                self.assertEqual(app.runtime_manifest, before)
                self.assertEqual(factory.candidate_store.list()[0].status, "proposed")
                editor.send("/exit")
                self.assertEqual(await asyncio.wait_for(running, 3), 0)
                self.assertIn("Automatic search includes", output.getvalue())
                self.assertIn("Independent cases", output.getvalue())
            finally:
                if not running.done():
                    running.cancel()
                await asyncio.gather(running, return_exceptions=True)

    async def test_generated_python_exercise_uses_its_own_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app, factory, provider, _ = await self.open_app(root, "failure-distillation")
            provider.respond_text("wrong")
            provider.respond_text("wrong")
            provider.respond_text(json.dumps({"tasks": [{"source_case_id": TaskCase("say A", "A").case_id,
                "policy_id": "python-function-tests-v1", "input": "Implement letter(), returning the string A.",
                "acceptance": {"entry_point": "letter", "tests": [{"args": [], "expected": "A"}]}}]}))
            provider.respond_text('{"accepted": true, "reason": "A small exercise of the required answer."}')
            provider.respond_text("def letter(): return 'wrong'")
            provider.respond_text('["Improved coding and answer guidance"]')
            provider.respond_text("def letter(): return 'A'")
            provider.respond_text("B")
            provider.respond_text("A")
            provider.respond_text("wrong")
            provider.respond_text("SECRET_ANSWER")
            preview = app.improvement_preview(pack_id="project", direction="Improve")
            records = await app.improve("Improve", preview_token=preview.preview_token)
            self.assertEqual(len(records), 1)
            history = root / dict(records[0].evidence)["Search history"]
            rows = [json.loads(line) for line in history.read_text().splitlines()]
            learning = [r for r in rows if r["kind"] == "batch-trial" and r["stage"] == "learning"]
            self.assertEqual([r["score"] for r in learning], [0.0, 1.0])
            self.assertIn("python-function-tests-v1", provider.calls[5]["messages"][0].content)
            self.assertEqual(factory.candidate_store.list()[0].report["candidate_train_score"], 1.0)
