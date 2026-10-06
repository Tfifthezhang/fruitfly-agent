"""Function-test policies through the native optimizer and the real terminal."""
import asyncio
import io
import json
from pathlib import Path
import tempfile
import unittest

from fruitfly_agent.interactive import TerminalFrontend
from tests.support import application as task_pack_helpers
from tests.support.optimizers import QueueEditor
from tests.support.task_packs import install
from tests.support.task_packs import coding_pack


class CodingOptimizationTests(unittest.IsolatedAsyncioTestCase):
    open_app = task_pack_helpers.open_task_app

    async def test_native_algorithms_share_real_function_scoring_and_feedback(self):
        for algorithm in ("opro",):
            with self.subTest(algorithm=algorithm), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp).resolve()
                install(root, coding_pack())
                app, factory, provider = await self.open_app(root, algorithm)
                for text in ("def double(x): return 0", "def add_one(x): return 0", '["Improved coding guidance"]',
                             "def add_one(x): return x+1", "def double(x): return x*2", '["Improved coding guidance"]'):
                    provider.respond_text(text)
                preview = app.optimization_preview(pack_id="coding", direction="Handle boundary cases")
                self.assertIn("restricted Python", dict(preview.details)["Code execution"])
                candidates = await app.optimize("Handle boundary cases", preview_token=preview.preview_token)
                self.assertTrue(candidates)
                evidence = dict(candidates[0].evidence)
                self.assertEqual("python-function-tests-v1", evidence["Evaluation policy"])
                self.assertIn("python-function-tests-v1", evidence["Task executor"])
                self.assertNotIn("SECRET_CODING_ANSWER", repr(provider.calls))
                self.assertNotIn("UNSEEN_CODING_TASK", repr(provider.calls))
                snapshot = (root / evidence["Task snapshot"]).read_text()
                self.assertNotIn("UNSEEN_FUNCTION", snapshot)
                history = [json.loads(line) for line in (root / evidence["Search history"]).read_text().splitlines()]
                observations = [r for r in history if r["kind"] == "trial"]
                self.assertTrue(all(r["policy_id"] == "python-function-tests-v1" for r in observations))
                self.assertTrue(candidates[0].parent_manifest_digest)
                self.assertIn(0, [r["score"] for r in observations])
                self.assertIn(1, [r["score"] for r in observations])
                self.assertTrue(any("got 0" in r["feedback"] for r in observations))
                self.assertIn("checks passed", repr(provider.calls))
                # Adoption remains the existing text-target path, not code deployment.
                before = app.runtime_manifest["digest"]
                adopted = await app.adopt_candidate(candidates[0].candidate_id)
                self.assertEqual("adopted", adopted.status)
                self.assertNotEqual(before, app.runtime_manifest["digest"])
                await app.close()

    async def test_terminal_package_preview_and_confirm_then_background_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            install(root, coding_pack())
            app, _, provider = await self.open_app(root, "opro")
            for text in ("def double(x): return 0", "def add_one(x): return 0", '["Coding guidance"]',
                         "def add_one(x): return x+1", "def double(x): return x*2", '["Coding guidance"]'):
                provider.respond_text(text)
            editor = QueueEditor()
            editor.send("/optimize improve", "1", "1", "1")
            output = io.StringIO()
            frontend = TerminalFrontend(app, input_stream=io.StringIO(), output_stream=output, line_editor=editor)
            running = asyncio.create_task(frontend.run())
            for _ in range(200):
                if app._optimization_task is not None:
                    break
                await asyncio.sleep(.01)
            await app.wait_for_optimization()
            editor.send("/exit")
            await running
            self.assertEqual(1, len(app.candidates()))
            self.assertIn("Code execution", output.getvalue())
            self.assertIn("python-function-tests-v1", output.getvalue())
            self.assertIn("Optimization submitted", output.getvalue())
