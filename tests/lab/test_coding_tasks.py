"""Generated function checks, policy isolation, resource bounds and cancellation."""
import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fruitfly_agent.lab.optimization.scoring import python_case, score_python, task_policy
from fruitfly_agent.lab.optimization.task_packs import TaskPackCatalog, load_pack
from tests.support.task_packs import install
from tests.support.task_packs import coding_pack

EXAMPLE = Path(__file__).resolve().parents[2] / "examples/optimization/python_functions"




class CodingTaskTests(unittest.IsolatedAsyncioTestCase):
    async def test_equivalent_implementations_and_code_fences_pass(self):
        case = python_case(coding_pack()["train"][0])
        for source in ("def add_one(value): return value + 1", "def add_one(value): return 1 + value",
            "```python\ndef add_one(value):\n    return value + 1\n```"):
            with self.subTest(source=source):
                result = await score_python(source, case)
                self.assertEqual(1.0, result.score)
                self.assertEqual("2/2 checks passed", result.feedback)

    async def test_partial_passes_exceptions_and_strict_booleans(self):
        case = python_case(dict(input="f", entry_point="f", tests=[dict(args=[0], expected=0), dict(args=[1], expected=2)]))
        result = await score_python("def f(x): return x", case)
        self.assertEqual(.5, result.score)
        self.assertIn("expected 2, got 1", result.feedback)
        case = python_case(dict(input="f", entry_point="f", tests=[dict(args=[], expected=True)]))
        self.assertEqual(0, (await score_python("def f(): return 1", case)).score)
        case = python_case(dict(input="f", entry_point="f", tests=[dict(args=[], raises="ValueError")]))
        self.assertEqual(1, (await score_python("def f(): raise ValueError('bad')", case)).score)
        self.assertEqual(0, (await score_python("def f(): return 0", case)).score)

    async def test_wrong_outputs_and_invalid_code_are_scored_failures(self):
        case = python_case(coding_pack()["train"][0])
        for source in ("def add_one(x): return 0", "def wrong(x): return x", "def add_one(", "Here is some code.",
                       "```python\ndef add_one(x): return x\n```\nExplanation"):
            with self.subTest(source=source):
                result = await score_python(source, case)
                self.assertEqual(0, result.score)
                self.assertTrue(result.feedback)

    async def test_unsupported_apis_rejected_without_file_access(self):
        case = python_case(coding_pack()["train"][0])
        with tempfile.TemporaryDirectory() as tmp:
            canary = Path(tmp) / "canary"
            sources = (
                "import os\ndef add_one(x): return x + 1",
                f"def add_one(x): return open({str(canary)!r}, 'w')",
                "def add_one(x): return ().__class__.__base__.__subclasses__()",
                "def add_one(x): return eval('x+1')",
                "def add_one(x): return globals()",
                "def add_one(x): return '{0.__class__}'.format(x)",
                "def add_one(x): return __import__('os').system('true')",
                "@str\ndef add_one(x): return x + 1",
                "class X: pass\ndef add_one(x): return x+1",
                "def add_one(x):\n    call = len\n    return call([x])",
            )
            for source in sources:
                with self.subTest(source=source):
                    result = await score_python(source, case)
                    self.assertEqual(0, result.score)
                    self.assertIn("rejected", result.feedback)
            self.assertFalse(canary.exists())

    async def test_timeout_and_cancellation_reap_worker(self):
        case = python_case(coding_pack()["train"][0])
        code = "def add_one(x):\n    while True:\n        pass"
        result = await score_python(code, case, timeout=.15)
        self.assertEqual(0, result.score)
        self.assertIn("timed out", result.feedback)
        original = asyncio.create_subprocess_exec
        started = asyncio.Event()
        workers = []
        async def capture(*args, **kwargs):
            self.assertEqual({}, kwargs["env"])
            self.assertIn("-I", args)
            process = await original(*args, **kwargs)
            workers.append(process)
            started.set()
            return process
        with patch("fruitfly_agent.lab.optimization.scoring.asyncio.create_subprocess_exec", side_effect=capture):
            task = asyncio.create_task(score_python(code, case))
            await asyncio.wait_for(started.wait(), 1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertIsNotNone(workers[0].returncode)

    async def test_literal_verifier_contract_rejects_executable_or_unbounded_tests(self):
        for mutate in (lambda r: r.update(tests=[]), lambda r: r.update(entry_point="__globals__"),
            lambda r: r.update(tests=[dict(args=[], expected=1, raises="ValueError")]),
            lambda r: r.update(tests=[dict(args=[], code="assert True")]),
            lambda r: r.update(tests=[dict(args=[], raises=[])]),
            lambda r: r.update(tests=[dict(kwargs={1:2}, expected=1)]),
            lambda r: r.update(tests=[dict(args=["x" * 1001], expected=1)])):
            row = json.loads(json.dumps(coding_pack()["train"][0]))
            mutate(row)
            with self.subTest(row=row), self.assertRaises(ValueError):
                python_case(row)

    async def test_all_example_references_pass_declared_checks(self):
        pack = load_pack(EXAMPLE.parents[2], EXAMPLE / "pack.json").material
        refs = json.loads((EXAMPLE / "references.json").read_text())
        policy = task_policy(pack["objective"]["policy_id"])
        for partition in ("train", "validation", "holdout"):
            for row in pack[partition]:
                with self.subTest(case=row["id"]):
                    self.assertEqual(1, (await policy.score(refs[row["id"]], policy.project(row))).score)

    async def test_frozen_tests_and_executor_identity_and_holdout_exclusion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            path = install(root, coding_pack())
            catalog = TaskPackCatalog(root, legacy_path=str(path.relative_to(root)))
            self.assertEqual("coding", catalog.default_pack_id)
            self.assertEqual(1, len(catalog.summaries()))
            suite = catalog.freeze("coding", "base_prompt")
            self.assertEqual("python-function-tests-v1", suite.policy_id)
            self.assertIn("python-function-tests-v1", suite.execution_id)
            self.assertNotIn("SECRET_CODING_ANSWER", repr(suite))
            self.assertIn('"expected":1', suite.train[0].verification)
            pack = coding_pack()
            pack["train"][0]["tests"][0]["expected"] = 99
            install(root, pack)
            self.assertNotEqual(suite.digest, catalog.freeze("coding", "base_prompt").digest)
            self.assertIn('"expected":1', suite.train[0].verification)
            self.assertIn("SECRET_CODING_ANSWER", catalog.holdout("coding")[0].verification)

    async def test_corrections_keep_tests_and_new_coding_tasks_need_verifier(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            path = install(root, coding_pack())
            catalog = TaskPackCatalog(root)
            before = load_pack(root, path).material
            row = before["train"][0]
            catalog.save_training("coding", row["input"], "def add_one(x): return x+1", expected_hash=catalog.source_hash("coding"), acceptance={"entry_point": row["entry_point"], "tests": row["tests"]})
            after = load_pack(root, path).material
            self.assertEqual(row["tests"], after["train"][0]["tests"])
            self.assertEqual(before["validation"], after["validation"])
            with self.assertRaisesRegex(ValueError, "entry_point/tests"):
                catalog.save_training("coding", "new task", "def f(): return 1", expected_hash=catalog.source_hash("coding"))

    async def test_preserve_args_detects_correct_answer_with_input_mutation(self):
        row = dict(input="Sort without mutating input", entry_point="f",
                   tests=[dict(args=[[2, 1]], expected=[1, 2], preserve_args=True)])
        case = python_case(row)
        result = await score_python("def f(values):\n    values.sort()\n    return values", case)
        self.assertEqual(0, result.score)
        self.assertIn("input arguments mutated", result.feedback)
        self.assertEqual(1, (await score_python("def f(values): return sorted(values)", case)).score)
