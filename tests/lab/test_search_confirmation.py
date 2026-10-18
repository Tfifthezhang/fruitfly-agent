"""Independent confirmation is one-shot and cannot conceal per-case regressions."""
import asyncio
from dataclasses import replace
import unittest

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.lab.algorithms.retained import RetainedText
from fruitfly_agent.lab.improvement.contracts.search import ImprovementProblem, TaskCase, SearchCandidate, SearchResult
from fruitfly_agent.lab.improvement.runtime.confirmation import confirm_result
from fruitfly_agent.lab.improvement.runtime.services import NativeSearchServices, SearchBudget, SearchJournal
from tests.support.faux_provider import FauxProvider


class SearchConfirmationTests(unittest.IsolatedAsyncioTestCase):
    def setup_services(self, evaluator):
        target = RetainedText('skill-document', 'baseline', 'Skill', 'skill-document-v1')
        problem = ImprovementProblem('job', 'parent', target.snapshot(), '', (TaskCase('train', 'A'),),
            (TaskCase('selection', 'B'),), 'cases', 'execution')
        services = NativeSearchServices(problem, AgentLoopConfig(provider=FauxProvider()), target,
            budget=SearchBudget(10, 10), journal=SearchJournal(problem), evaluator=evaluator)
        cases = (TaskCase('unseen one', 'C'), TaskCase('unseen two', 'D'))
        return problem, services, cases

    async def test_aggregate_tie_cannot_hide_per_case_regression_or_retry_another_candidate(self):
        def scores(text, case):
            if text == 'baseline':
                return float(case.input == 'unseen two')
            if text == 'selected':
                return float(case.input == 'unseen one')
            return 1.
        problem, services, cases = self.setup_services(scores)
        result = SearchResult((SearchCandidate('selected', 1.), SearchCandidate('runner-up', .9)), .5)
        confirmed = await confirm_result(problem, services, result, cases)
        self.assertEqual(confirmed.candidates, ())
        self.assertEqual(confirmed.stop_reason, 'confirmation_failed')
        attempted = [r['candidate_id'] for r in services.history() if r['kind'] == 'batch-trial-start']
        self.assertEqual(len(attempted), 4)
        self.assertEqual(services.budget.used['trial'], 4)

    async def test_holdout_tie_passes_only_after_strict_selection_improvement(self):
        problem, services, cases = self.setup_services(lambda _text, _case: 1.)
        result = SearchResult((SearchCandidate('candidate', 1.),), .5)
        confirmed = await confirm_result(problem, services, result, cases)
        self.assertEqual(confirmed.stop_reason, 'confirmed')
        self.assertEqual(len(confirmed.candidates), 1)
        problem, services, cases = self.setup_services(lambda _text, _case: 1.)
        tied = SearchResult((SearchCandidate('candidate', .5),), .5)
        self.assertEqual((await confirm_result(problem, services, tied, cases)).stop_reason, 'selection_not_improved')
        self.assertEqual(services.history(), ())

    async def test_confirmation_cancellation_never_returns_a_candidate(self):
        entered = asyncio.Event()
        async def blocked(_text, _case):
            entered.set()
            await asyncio.Event().wait()
        problem, services, cases = self.setup_services(blocked)
        result = SearchResult((SearchCandidate('candidate', 1.),), .5)
        task = asyncio.create_task(confirm_result(problem, services, result, cases))
        await entered.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(any(r['kind'] == 'batch-trial-stop' for r in services.history()))
