"""Learning gains cannot substitute for original-task and independent gains."""
import asyncio
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.data_model import AgentToolResult, TextBlock
from fruitfly_agent.core.tool_runtime import AgentTool
from fruitfly_agent.lab.base_prompt.target import BasePromptTarget
from fruitfly_agent.lab.improvement.automatic import AutomaticPolicy, AutomaticWorkflow
from fruitfly_agent.lab.improvement.trials.execution import IsolatedHarnessExecutor, PreparedTrial
from fruitfly_agent.lab.improvement.failure_processing import ReplayFailureProcessor, LearningMaterial, LearningTask
from fruitfly_agent.lab.improvement.runtime.host import HostedTextImprover
from fruitfly_agent.lab.improvement.methods.opro import OproImprover
from fruitfly_agent.lab.improvement.tasks.scoring import ScoreResult
from fruitfly_agent.lab.improvement.contracts.search import SearchCandidate, SearchResult, TaskCase
from fruitfly_agent.lab.improvement.runtime.services import NativeSearchServices, BudgetExhausted
from fruitfly_agent.lab.improvement.tasks import TaskPackCatalog
from tests.support.faux_provider import FauxProvider
from tests.support.search import services, tool_calls
from tests.support.task_packs import install, package


class AutomaticImprovementTests(unittest.IsolatedAsyncioTestCase):
    def host(self, root, provider, evaluate, *, policy=None, processor=None, budget=64):
        class DeterministicServices(NativeSearchServices):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs, evaluator=evaluate)
        parameters = {"target": "base_prompt", "cases_path": ".fruitfly/improvement/task-packs/project/pack.json",
                      "rounds": 3, "batch_size": 2, "history_limit": 5,
                      "max_metric_calls": budget, "max_model_calls": 64,
                      "call_timeout_seconds": 1, "output_max_tokens": 1024}
        host = HostedTextImprover(OproImprover(), AgentLoopConfig(provider=provider, system_prompt="seed"),
            root, parameters, target=BasePromptTarget("seed"), label="OPRO", services_factory=DeterministicServices)
        host.configure_workflow(AutomaticWorkflow(processor or ReplayFailureProcessor(), policy))
        return host

    def rows(self, root):
        path = next((root / ".fruitfly/improvement/searches").glob("*.jsonl"))
        return [json.loads(line) for line in path.read_text().splitlines()]

    async def test_confirmed_gain_stops_early_and_never_activates_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install(root)
            provider = FauxProvider()
            provider.respond_text('["candidate", "unused candidate"]')
            host = self.host(root, provider, lambda text, _case: float(text == "candidate"))
            preview = host.preview()
            self.assertIn("human adoption", dict(preview.details)["Workflow"])
            result = await host.search("seed", "Improve task success", parent_manifest="parent")
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0].report.stop_reason, "confirmed_improvement")
            self.assertEqual(result[0].report.trial_calls, 8)
            self.assertEqual(host.target.snapshot().text, "seed")
            self.assertEqual(len(provider.calls), 1)
            self.assertNotIn("UNSEEN_INPUT", provider.calls[0]["messages"][0].content)
            self.assertNotIn("SECRET_ANSWER", provider.calls[0]["messages"][0].content)
            self.assertEqual(dict(result[0].evidence)["Confirmation candidate score"], "1.0")
            rows = self.rows(root)
            self.assertEqual(len([r for r in rows if r["kind"] == "opro-attempt"]), 1)
            self.assertEqual(len([r for r in rows if r["kind"] == "confirmation-result"]), 1)

    async def test_learning_only_gain_never_reaches_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install(root)
            provider = FauxProvider()
            for text in ('["candidate"]', '["second"]', '["third"]'):
                provider.respond_text(text)
            host = self.host(root, provider, lambda text, case: float(text != "seed" and case.input == "say A"))
            self.assertEqual(await host.search("seed", "Improve", parent_manifest="parent"), ())
            rows = self.rows(root)
            self.assertFalse(any(r["kind"] == "confirmation-start" for r in rows))
            self.assertEqual(rows[-1]["status"], "no_improvement")

    async def test_non_observing_strategy_scores_cannot_replace_original_selection(self):
        class ExternalStrategy:
            supported_schemas = frozenset({"text-v1"})
            async def search(self, problem, service):
                return SearchResult((SearchCandidate("candidate", 99.0),), 0.0)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install(root)
            host = self.host(root, FauxProvider(),
                lambda text, case: float(text == "candidate" and case.input != "say B"))
            host.strategy = ExternalStrategy()
            self.assertEqual(await host.search("seed", "Improve", parent_manifest="parent"), ())
            rows = self.rows(root)
            self.assertFalse(any(r["kind"] == "confirmation-start" for r in rows))
            selection = [r for r in rows if r["kind"] == "evaluation" and r["text"] == "candidate"]
            self.assertEqual([(r["partition"], r["score"]) for r in selection], [("validation", 0.0)])

    async def test_confirmation_repeats_use_fresh_trials_in_the_root_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install(root)
            provider = FauxProvider()
            provider.respond_text('["candidate"]')
            host = self.host(root, provider, lambda text, _case: float(text == "candidate"),
                             policy=AutomaticPolicy(confirmation_repeats=3))
            result = await host.search("seed", "Improve", parent_manifest="parent")
            self.assertEqual(result[0].report.trial_calls, 12)
            confirmation = [r for r in self.rows(root)
                            if r["kind"] == "batch-trial" and r["stage"] == "confirmation"]
            self.assertEqual([r["repeat"] for r in confirmation], [0, 1, 2, 0, 1, 2])
            self.assertEqual(len({r["evaluation_id"] for r in confirmation}), 6)

    async def test_holdout_failure_stops_without_retrying_the_same_holdout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install(root)
            provider = FauxProvider()
            provider.respond_text('["candidate"]')
            host = self.host(root, provider, lambda text, case: float(text == "candidate" and case.input != "UNSEEN_INPUT"))
            self.assertEqual(await host.search("seed", "Improve", parent_manifest="parent"), ())
            rows = self.rows(root)
            self.assertEqual(rows[-1]["status"], "confirmation_failed")
            self.assertEqual(len([r for r in rows if r["kind"] == "confirmation-start"]), 1)
            self.assertEqual(len(provider.calls), 1)

    async def test_per_case_regression_rejects_a_higher_selection_score(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = package()
            payload["train"].append(dict(id="train-preserved", input="already works", expected="OK"))
            install(root, payload)
            provider = FauxProvider()
            provider.respond_text('["regressive", "candidate"]')
            def evaluate(text, case):
                if case.input == "already works":
                    return float(text != "regressive")
                return float(text != "seed")
            host = self.host(root, provider, evaluate)
            result = await host.search("seed", "Improve", parent_manifest="parent")
            self.assertEqual(result[0].text, "candidate")
            self.assertTrue(any(r["kind"] == "automatic-candidate-rejected" for r in self.rows(root)))

    async def test_budget_exhaustion_during_confirmation_publishes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install(root)
            provider = FauxProvider()
            provider.respond_text('["candidate"]')
            host = self.host(root, provider, lambda text, _case: float(text == "candidate"), budget=7)
            self.assertEqual(await host.search("seed", "Improve", parent_manifest="parent"), ())
            self.assertEqual(self.rows(root)[-1]["status"], "budget_exhausted")
            self.assertEqual(host.target.snapshot().text, "seed")

    async def test_unscored_baseline_is_not_learned_as_a_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install(root)
            provider = FauxProvider()
            def broken(_text, _case):
                raise RuntimeError("infrastructure unavailable")
            host = self.host(root, provider, broken)
            self.assertEqual(await host.search("seed", "Improve", parent_manifest="parent"), ())
            self.assertEqual(provider.calls, [])
            self.assertEqual(self.rows(root)[-1]["status"], "baseline_unavailable")

    async def test_holdout_overlap_is_rejected_before_candidate_generation(self):
        class Overlap:
            implementation_id = "overlap-v1"
            async def process(self, failures, service, *, policy, limit):
                return LearningMaterial((LearningTask(TaskCase("UNSEEN_INPUT", "bad"),
                    failures[0].case.case_id, self.implementation_id, "test review"),), self.implementation_id)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install(root)
            provider = FauxProvider()
            host = self.host(root, provider, lambda *_: 0.0, processor=Overlap())
            with self.assertRaisesRegex(ValueError, "overlapping"):
                await host.search("seed", "Improve", parent_manifest="parent")
            self.assertEqual(provider.calls, [])

    async def test_missing_holdout_and_changed_package_fail_without_model_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = package()
            payload["files"].pop("holdout")
            payload.pop("holdout")
            path = install(root, payload)
            provider = FauxProvider()
            host = self.host(root, provider, lambda *_: 0.0)
            with self.assertRaisesRegex(ValueError, "holdout"):
                host.preview()
            payload = package()
            path = install(root, payload)
            host = self.host(root, provider, lambda *_: 0.0)
            frozen = host.task_source.freeze("project", "base_prompt")
            host.preview(task=frozen)
            path.write_text(path.read_text() + " ")
            with self.assertRaisesRegex(ValueError, "changed"):
                await host.search("seed", "Improve", parent_manifest="parent", task=frozen)
            self.assertEqual(provider.calls, [])

    async def test_timeout_cleans_up_and_does_not_publish_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install(root)
            cleaned = asyncio.Event()
            async def blocked(*_):
                try:
                    await asyncio.Event().wait()
                finally:
                    cleaned.set()
            host = self.host(root, FauxProvider(), blocked, policy=AutomaticPolicy(timeout_seconds=.01))
            self.assertEqual(await host.search("seed", "Improve", parent_manifest="parent"), ())
            self.assertTrue(cleaned.is_set())
            self.assertEqual(self.rows(root)[-1]["status"], "workflow_timeout")

    async def test_external_executor_runs_multiple_tool_steps_and_closes_fresh_state(self):
        provider = FauxProvider()
        tool_calls(provider, [("set_value", {"value": 2})])
        provider.respond_text("done")
        closed = []
        def prepare(config, case):
            state = {"value": 0}
            async def set_value(ctx):
                state["value"] = ctx.args["value"]
                return AgentToolResult(content=[TextBlock(text="updated")])
            tool = AgentTool(name="set_value", label="Set value", description="Update the isolated task state.",
                parameters={"type": "object", "properties": {"value": {"type": "integer"}}, "required": ["value"]}, execute=set_value)
            return PreparedTrial(replace(config, tools=(tool,)),
                verify=lambda result, case: ScoreResult(float(state["value"] == 2), "final state checked"),
                close=lambda: closed.append(dict(state)))
        service = services(provider, trial_executor=IsolatedHarnessExecutor(prepare))
        result = await service.evaluate("candidate", "validation")
        self.assertEqual(result.score, 1.0)
        self.assertEqual(service.budget.used, {"model": 2, "trial": 1})
        self.assertEqual(closed, [{"value": 2}])
        self.assertEqual(service.config.tools, ())

    async def test_external_executor_cannot_bypass_budget_or_leak_task_resources(self):
        provider = FauxProvider()
        tool_calls(provider, [("read", {"path": "task"})])
        closed = []
        async def read(ctx):
            return AgentToolResult(content=[TextBlock(text="read")])
        def prepare(config, case):
            tool = AgentTool(name="read", label="Read", description="Read task-owned state.",
                parameters={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}, execute=read)
            return PreparedTrial(replace(config, tools=(tool,)), lambda *_: ScoreResult(1), close=lambda: closed.append(True))
        service = services(provider, model_calls=1, trial_executor=IsolatedHarnessExecutor(prepare))
        with self.assertRaises(BudgetExhausted):
            await service.evaluate("candidate", "validation")
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(closed, [True])
