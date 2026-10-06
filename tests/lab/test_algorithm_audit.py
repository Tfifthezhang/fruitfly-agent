"""Regression evidence for the Lab developer-guide audit; fully offline."""

import asyncio
import tempfile
from pathlib import Path
import unittest

from fruitfly_agent.core.data_model import (
    ContextDecision, ContextSnapshot, UserMessage,
)
from fruitfly_agent.lab.context_manager.augmentation.information import (
    InformationArtifact, InformationHit, InformationQuery,
    InformationRef, TextInformationApplicator,
)
from fruitfly_agent.lab.context_manager.augmentation.information.application import (
    INFORMATION_BLOCK_START, INFORMATION_BLOCK_END,
)
from fruitfly_agent.lab.context_manager.reduction import (
    SummarizingCompactor, SummarizingCompactorConfig,
)
from fruitfly_agent.lab.context_manager.reduction.cut import find_cut_point
from tests.support.faux_provider import FauxProvider
from fruitfly_agent.core.tool_runtime import ToolCallContext
from fruitfly_agent.core.env import ExecOptions
from fruitfly_agent.lab.environment import LocalEnv


def _snapshot():
    return ContextSnapshot(
        (), (UserMessage(content="old"), UserMessage(content="latest")),
        "", (), 1, "offline", 16, "overflow", overflow_attempt=1,
    )


class EditAuditTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = LocalEnv(cwd=str(self.root))

    async def run_tool(self, tool, args):
        return await tool.execute(ToolCallContext(
            tool_call_id="audit", name=tool.name, args=args, env=self.env,
        ))

    async def test_edits_match_original_even_when_replacement_creates_duplicates(self):
        from fruitfly_agent.lab.tools import create_edit_tool
        path = self.root / "original.txt"
        path.write_text("alpha\nbeta\n", encoding="utf-8")
        await self.run_tool(create_edit_tool(), {"path": path.name, "edits": [
            {"oldText": "alpha", "newText": "beta"},
            {"oldText": "beta", "newText": "gamma"},
        ]})
        self.assertEqual("beta\ngamma\n", path.read_text())

    async def test_overlapping_original_spans_fail_without_writing(self):
        from fruitfly_agent.lab.tools import create_edit_tool
        path = self.root / "overlap.txt"
        original = "alpha beta gamma\n"
        path.write_text(original, encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "overlap"):
            await self.run_tool(create_edit_tool(), {"path": path.name, "edits": [
                {"oldText": "alpha beta", "newText": "replaced"},
                {"oldText": "beta gamma", "newText": "second"},
            ]})
        self.assertEqual(original, path.read_text())

    async def test_multiline_fuzzy_match_replaces_entire_span(self):
        from fruitfly_agent.lab.tools import create_edit_tool
        path = self.root / "fuzzy.txt"
        path.write_text("original line\nsecond line\nkeep\n", encoding="utf-8")
        await self.run_tool(create_edit_tool(), {"path": path.name, "edits": [
            {"oldText": "origina line\nsecond line", "newText": "fixed"},
        ]})
        self.assertEqual("fixed\nkeep\n", path.read_text())

    async def test_empty_or_ambiguous_match_never_writes(self):
        from fruitfly_agent.lab.tools import create_edit_tool
        for original, old in (
            ("alpha", ""),
            ("original line\noriginal lime\n", "original liXe"),
            ("aaaa", "aaa"),
        ):
            with self.subTest(original=original, old=old):
                path = self.root / "invalid.txt"
                path.write_text(original, encoding="utf-8")
                with self.assertRaises(RuntimeError):
                    await self.run_tool(create_edit_tool(), {"path": path.name, "edits": [
                        {"oldText": old, "newText": "changed"},
                    ]})
                self.assertEqual(original, path.read_text())


class CutAndInformationAuditTests(unittest.TestCase):
    def test_larger_retention_budget_keeps_more_complete_turns(self):
        messages = [UserMessage(content=str(index)) for index in range(4)]
        self.assertEqual(3, find_cut_point(messages, 10, lambda _: 10))
        self.assertEqual(1, find_cut_point(messages, 30, lambda _: 10))
        self.assertIsNone(find_cut_point(messages, 40, lambda _: 10))

    def test_information_budget_includes_headers_references_and_markers(self):
        hits = [InformationHit(InformationArtifact(
            InformationRef("docs", str(i)), "x" * 500,
        ), 1.0) for i in range(3)]
        for target in ("system_prompt", "messages", "tool"):
            for budget in (1, 100, 256, 600):
                with self.subTest(target=target, budget=budget):
                    effect = TextInformationApplicator(target).apply(
                        InformationQuery("x", top_k=2, max_chars=budget), hits,
                    )
                    if effect is None:
                        continue
                    rendered = effect.content
                    if target == "system_prompt":
                        rendered = f"{INFORMATION_BLOCK_START}\n{rendered}\n{INFORMATION_BLOCK_END}"
                    self.assertLessEqual(len(rendered), budget)
                    self.assertLessEqual(len(effect.refs), 2)


class EnvironmentAuditTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_cwd_and_fast_command_with_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = await asyncio.wait_for(
                LocalEnv(tmp).exec("pwd", ExecOptions(timeout_seconds=10)), 2,
            )
            self.assertTrue(result.is_ok, result.error)
            self.assertEqual(Path(tmp).resolve(), Path(result.unwrap().stdout.strip()).resolve())

    async def test_long_output_line_is_not_a_stream_limit_error(self):
        result = await LocalEnv().exec("python3 -c 'print(\"x\" * 100000)'")
        self.assertTrue(result.is_ok, result.error)
        self.assertEqual(100001, len(result.unwrap().stdout))

    async def test_stdout_update_arrives_before_command_exits(self):
        updated = asyncio.Event()
        async def on_stdout(text):
            if "ready" in text:
                updated.set()
        task = asyncio.create_task(LocalEnv().exec(
            "echo ready; sleep 30", ExecOptions(on_stdout=on_stdout),
        ))
        try:
            await asyncio.wait_for(updated.wait(), 2)
            self.assertFalse(task.done())
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


class ReductionAuditTests(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_summarizer_never_proposes_overflow_projection(self):
        provider = FauxProvider()
        compactor = SummarizingCompactor(SummarizingCompactorConfig(enabled=False), provider)
        self.assertIsNone(await compactor.react_to_overflow(_snapshot(), RuntimeError()))
        self.assertEqual([], provider.calls)

