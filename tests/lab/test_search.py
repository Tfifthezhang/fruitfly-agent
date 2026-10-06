"""Public optimization contracts, native execution and multi-strategy regression."""
import asyncio
from dataclasses import replace
from pathlib import Path
import json
import tempfile
import unittest

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.data_model import AssistantMessage, ToolCallBlock, TextBlock, Usage
from fruitfly_agent.lab.base_prompt.target import BasePromptTarget
from fruitfly_agent.lab.optimization.search import (
    TaskCase, OptimizationProblem, ObjectivePolicy, TrialObservation, content_id,
)
from fruitfly_agent.lab.optimization.services import NativeSearchServices, SearchBudget, SearchJournal, BudgetExhausted
from fruitfly_agent.lab.optimization.opro import OproOptimizer
from fruitfly_agent.lab.optimization.host import HostedTextOptimizer
from fruitfly_agent.lab.algorithms import Algorithm, AlgorithmSpec
from tests.support.faux_provider import FauxProvider
from tests.support.search import problem, services, tool_calls, engineer










class SearchContractTests(unittest.IsolatedAsyncioTestCase):
    def test_nonfinite_and_error_scores_are_rejected(self):
        fields = ("eval", "candidate", "case", "train", "runtime", "policy")
        for status, score in (("ok", float("nan")), ("ok", None), ("error", 0.0)):
            with self.assertRaises(ValueError):
                TrialObservation(*fields, status, score)
        self.assertTrue(ObjectivePolicy("loss-v1", "loss", "min").better(1.0, 2.0))
        self.assertFalse(ObjectivePolicy().better(0.0, 1.0))

    async def test_trials_record_real_usage_and_keep_production_isolated(self):
        provider = FauxProvider()
        provider.respond_text(" B ")
        s = services(provider)
        result = await s.evaluate("new target", "validation")
        self.assertEqual(result.score, 1)
        receipt = result.observations[0]
        self.assertEqual((receipt.candidate_id, receipt.case_id, receipt.partition),
                         (content_id("new target"), s.problem.validation[0].case_id, "validation"))
        self.assertEqual(receipt.execution_id, "runtime-1")
        request = next(r for r in s.history() if r["kind"] == "request")
        self.assertEqual(request["evaluation_id"], receipt.evaluation_id)
        self.assertEqual(request["candidate_id"], receipt.candidate_id)
        self.assertEqual(request["case_id"], receipt.case_id)
        self.assertEqual(s.budget.used, {"model": 1, "trial": 1})
        self.assertEqual(provider.calls[0]["tools"], [])
        self.assertEqual(provider.calls[0]["system_prompt"], "new target")
        self.assertEqual(s.config.system_prompt, "production")
        self.assertEqual(next(r for r in s.history() if r["kind"] == "response")["usage"]["output_tokens"], 5)
        history = s.history()
        history[0]["parent_manifest"] = "tampered"
        self.assertEqual(s.history()[0]["parent_manifest"], "parent-1")

    async def test_failed_or_truncated_trials_never_become_zero_scores(self):
        for truncated in (False, True):
            provider = FauxProvider()
            if truncated:
                provider.respond_text("B", stop_reason="length")
            else:
                provider.respond_fatal()
            result = await services(provider).evaluate("candidate", "validation")
            self.assertIsNone(result.score)
            self.assertEqual(result.observations[0].status, "error")
            self.assertIsNone(result.observations[0].score)

    async def test_budget_reserved_before_model_call_and_all_roles_share_it(self):
        provider = FauxProvider()
        provider.respond_text("B")
        s = services(provider, model_calls=1)
        await s.evaluate("candidate", "validation")
        with self.assertRaises(BudgetExhausted):
            await s.complete("meta", "meta", "prompt")
        self.assertEqual(len(provider.calls), 1)

    async def test_wrong_partition_is_rejected_without_calls(self):
        provider = FauxProvider()
        s = services(provider)
        with self.assertRaises(ValueError):
            await s.evaluate("candidate", "train", cases=s.problem.validation)
        self.assertEqual(provider.calls, [])

    async def test_new_model_free_strategy_uses_frozen_host_problem_and_shared_history(self):
        from tests.support.materials import _write_cases
        from fruitfly_agent.lab.optimization.search import SearchCandidate, SearchResult
        class Enumerate(Algorithm):
            spec = AlgorithmSpec("enumerate", "enumerate-v1")
            supported_schemas = frozenset({"text-v1"})
            required_capabilities = frozenset({"evaluate", "history"})
            async def search(self, p, s):
                self.problem = p
                seed = await s.evaluate(p.baseline.text, "validation")
                trial = await s.evaluate("candidate", "validation")
                return SearchResult((SearchCandidate("candidate", trial.score),), seed.score)
        class DeterministicServices(NativeSearchServices):
            capabilities = frozenset({"evaluate", "history"})
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs, evaluator=lambda text, _case: float(text == "candidate"))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_cases(root)
            provider, strategy = FauxProvider(), Enumerate()
            parameters = {"target": "base_prompt", "cases_path": ".fruitfly/optimization/cases.json",
                          "max_metric_calls": 4, "max_model_calls": 1, "call_timeout_seconds": 1, "output_max_tokens": 128}
            host = HostedTextOptimizer(strategy, AgentLoopConfig(provider=provider), root, parameters,
                target=BasePromptTarget("seed"), label="Enumerate", services_factory=DeterministicServices)
            host.preview()
            (root / parameters["cases_path"]).write_text("corrupt changed file")
            host.preview()  # Still the same approved suite.
            proposals = await host.search("seed", "improve", parent_manifest="frozen-parent")
            self.assertEqual(proposals[0].validation_score, 1)
            self.assertEqual(proposals[0].report.conclusion, 'improved')
            self.assertEqual(proposals[0].report.tokens.reported_calls, 0)
            self.assertEqual(proposals[0].report.trial_calls, 2)
            self.assertEqual(strategy.problem.parent_manifest, "frozen-parent")
            self.assertEqual(strategy.problem.train[0].expected, "A")
            self.assertEqual(provider.calls, [])
            history = root / dict(proposals[0].evidence)["Search history"]
            rows = [json.loads(line) for line in history.read_text().splitlines()]
            self.assertEqual(rows[-1]["usage"], {"model": 0, "trial": 2})
            with self.assertRaisesRegex(ValueError, "unavailable"):
                HostedTextOptimizer(OproOptimizer(), AgentLoopConfig(provider=provider), root, parameters,
                    target=BasePromptTarget("seed"), label="OPRO", services_factory=DeterministicServices)
            _write_cases(root)
            class FlakyServices(DeterministicServices):
                attempts = 0
                def __init__(self, *args, **kwargs):
                    type(self).attempts += 1
                    if self.attempts == 1:
                        raise ValueError("service construction failed")
                    super().__init__(*args, **kwargs)
            host = HostedTextOptimizer(strategy, AgentLoopConfig(provider=provider), root, parameters,
                target=BasePromptTarget("seed"), label="Enumerate", services_factory=FlakyServices)
            with self.assertRaisesRegex(ValueError, "construction failed"):
                await host.search("seed", "improve", parent_manifest="frozen-parent")
            self.assertFalse(host.cancel())
            self.assertEqual(len(await host.search("seed", "improve", parent_manifest="frozen-parent")), 1)

    async def test_empty_skill_baseline_and_idempotent_projection_remain_executable(self):
        from fruitfly_agent.lab.context_manager.augmentation.skills.target import SkillGuidanceTarget
        target = SkillGuidanceTarget("", 16000)
        p = problem(baseline=target.snapshot())
        provider = FauxProvider()
        provider.respond_text("B")
        s = services(provider, p=p)
        s.target = target
        self.assertEqual((await s.evaluate("", "validation")).score, 1)
        with self.assertRaises(ValueError):
            target.validate("")
        projected = target.prepare_trial(s.config, "new guidance")
        nonempty = SkillGuidanceTarget("new guidance", 16000)
        self.assertEqual(nonempty.prepare_trial(projected, "new guidance"), projected)

    async def test_cancelled_request_is_recorded_and_not_replayed(self):
        provider = FauxProvider()
        entered = asyncio.Event()
        async def blocked_events():
            entered.set()
            await asyncio.Event().wait()
            yield
        from fruitfly_agent.core.model_stream import AssistantMessageEventStream
        provider.script.append(lambda *_args, **_kwargs: AssistantMessageEventStream(blocked_events()))
        s = services(provider)
        task = asyncio.create_task(s.complete("optimizer", "s", "p"))
        await entered.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual([r for r in s.history() if r["kind"] == "response"][0]["status"], "cancelled")

    async def test_tool_agent_rejects_unconsumed_skill_and_unauthorized_path(self):
        provider = FauxProvider()
        tool_calls(provider, [("write", {"path": "context.txt", "content": "fake"})])
        provider.respond_text("done")
        s = services(provider)
        with self.assertRaisesRegex(ValueError, "did not produce"):
            await s.agent("base", "s", "p", files={"learning-context/SKILL.md": "method"}, output_path="context.txt")
        self.assertFalse(any(r["kind"] == "agent-write" for r in s.history()))
        provider = FauxProvider()
        tool_calls(provider, [("read", {"path": "../../secret"})])
        provider.respond_text("done")
        s = services(provider)
        with self.assertRaises(ValueError):
            await s.agent("base", "s", "p", files={}, output_path="context.txt")
        self.assertFalse(any(r["kind"] == "agent-read" for r in s.history()))

    async def test_opro_history_dedup_and_minimization(self):
        provider = FauxProvider()
        for text in ("2", "2", '["worse", "better"]', "3", "3", "1", "1", '["better", "seed"]'):
            provider.respond_text(text)
        p = problem(policy=ObjectivePolicy("loss-v1", "loss", "min"))
        s = services(provider, p=p, scorer=lambda output, _case: float(output))
        result = await OproOptimizer().search(p, s)
        self.assertEqual([c.text for c in result.candidates], ["better", "worse"])
        self.assertEqual(result.seed_score, 2)
        second_prompt = json.loads(provider.calls[-1]["messages"][0].content)
        self.assertEqual([h["score"] for h in second_prompt["history"]], [3, 2, 1])
        self.assertNotIn("select", provider.calls[-1]["messages"][0].content)
        self.assertEqual(len([r for r in s.history() if r["kind"] == "proposal-rejected"]), 2)

    async def test_invalid_opro_response_continues_and_budget_stops_cleanly(self):
        provider = FauxProvider()
        for text in ("wrong", "wrong", "not JSON", '["candidate"]', "A", "B"):
            provider.respond_text(text)
        s = services(provider, model_calls=5)
        result = await OproOptimizer().search(s.problem, s)
        self.assertEqual(result.stop_reason, "budget_exhausted")
        self.assertEqual(result.candidates, ())  # no complete selection receipt
        self.assertEqual(len(provider.calls), 5)
        self.assertTrue(any(r["kind"] == "proposal-error" for r in s.history()))



    def test_journal_new_identity_and_pending_request_survive_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "history.jsonl"
            journal = SearchJournal(problem(), path)
            attempt = journal.append("request", status="pending", role="meta")
            saved = json.loads(path.read_text())
            self.assertEqual(saved["id"], attempt)
            with self.assertRaises(FileExistsError):
                SearchJournal(problem(), path)


if __name__ == "__main__":
    unittest.main()
