"""Derived exercises preserve provenance and require separate, bounded material review."""
import asyncio
import json
import unittest

from fruitfly_agent.lab.optimization.failure_processing import (
    FailureExample, ReplayFailureProcessor, ModelDistillationProcessor,
)
from fruitfly_agent.lab.optimization.scoring import task_policy
from fruitfly_agent.lab.optimization.search import TrialObservation
from fruitfly_agent.lab.optimization.services import BudgetExhausted
from tests.support.search import services
from tests.support.faux_provider import FauxProvider


class FailureProcessingTests(unittest.IsolatedAsyncioTestCase):
    def example(self, service):
        case = service.problem.train[0]
        receipt = TrialObservation("trial", "candidate", case.case_id, "train",
                                   "runtime-1", "normalized-exact-v1", "ok", 0.0, "wrong", "wrong label")
        return FailureExample(case, receipt)

    def generation(self, example, **changes):
        row = {"source_case_id": example.case.case_id, "input": "Learning exercise: return A",
               "acceptance": {"expected": "A"}}
        return json.dumps({"tasks": [{**row, **changes}]})

    async def test_replay_keeps_original_acceptance_and_makes_no_model_calls(self):
        provider = FauxProvider()
        service = services(provider)
        example = self.example(service)
        result = await ReplayFailureProcessor().process((example,), service,
                                                       policy=task_policy("normalized-exact-v1"), limit=2)
        self.assertEqual(result.tasks[0].case, example.case)
        self.assertEqual(result.tasks[0].source_case_id, example.case.case_id)
        self.assertEqual(provider.calls, [])

    async def test_distillation_creates_different_tasks_and_records_review(self):
        provider = FauxProvider()
        service = services(provider)
        example = self.example(service)
        provider.respond_text(self.generation(example))
        provider.respond_text('{"accepted": true, "reason": "The requirement and answer agree."}')
        result = await ModelDistillationProcessor().process((example,), service,
            policy=task_policy("normalized-exact-v1"), limit=2)
        self.assertNotEqual(result.tasks[0].case.input, example.case.input)
        self.assertEqual(result.tasks[0].case.expected, "A")
        self.assertEqual(result.tasks[0].source_case_id, example.case.case_id)
        self.assertEqual(service.budget.used["model"], 2)
        self.assertEqual([r["role"] for r in service.history() if r["kind"] == "generation"],
                         ["materializer", "material_reviewer"])
        self.assertTrue(next(r for r in service.history() if r["kind"] == "material-review")["accepted"])

    async def test_unknown_source_and_unsafe_acceptance_fail_before_review(self):
        for change in ({"source_case_id": "another-source"},
                       {"acceptance": {"expected": "A", "command": "run arbitrary code"}},
                       {"input": ""}):
            with self.subTest(change=change):
                provider = FauxProvider()
                service = services(provider)
                provider.respond_text(self.generation(self.example(service), **change))
                with self.assertRaises(ValueError):
                    await ModelDistillationProcessor().process((self.example(service),), service,
                        policy=task_policy("normalized-exact-v1"), limit=2)
                self.assertEqual(len(provider.calls), 1)

    async def test_rejected_or_malformed_review_does_not_publish_material(self):
        for review in ('{"accepted": false, "reason": "Incorrect acceptance."}',
                       '{"accepted": "true", "reason": "Incorrect type."}',
                       '{"accepted": true, "accepted": false, "reason": "Duplicate field."}'):
            with self.subTest(review=review):
                provider = FauxProvider()
                service = services(provider)
                provider.respond_text(self.generation(self.example(service)))
                provider.respond_text(review)
                with self.assertRaises(ValueError):
                    await ModelDistillationProcessor().process((self.example(service),), service,
                        policy=task_policy("normalized-exact-v1"), limit=2)

    async def test_generation_and_review_share_the_root_model_budget(self):
        provider = FauxProvider()
        service = services(provider, model_calls=1)
        provider.respond_text(self.generation(self.example(service)))
        with self.assertRaises(BudgetExhausted):
            await ModelDistillationProcessor().process((self.example(service),), service,
                policy=task_policy("normalized-exact-v1"), limit=2)
        self.assertEqual(len(provider.calls), 1)

    async def test_cancelled_review_is_not_accepted_or_replayed(self):
        from fruitfly_agent.core.model_stream import AssistantMessageEventStream
        provider = FauxProvider()
        service = services(provider)
        provider.respond_text(self.generation(self.example(service)))
        entered, cleaned = asyncio.Event(), asyncio.Event()
        async def wait():
            entered.set()
            try:
                await asyncio.Event().wait()
                yield
            finally:
                cleaned.set()
        provider.script.append(lambda *_args, **_kwargs: AssistantMessageEventStream(wait()))
        running = asyncio.create_task(ModelDistillationProcessor().process((self.example(service),), service,
            policy=task_policy("normalized-exact-v1"), limit=2))
        await asyncio.wait_for(entered.wait(), 1)
        running.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await running
        self.assertTrue(cleaned.is_set())
        self.assertFalse(any(r["kind"] == "material-review" for r in service.history()))
