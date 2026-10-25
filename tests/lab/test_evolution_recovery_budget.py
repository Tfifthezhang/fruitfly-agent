"""Durable root allowances cannot be reset by coordinator restart."""
import unittest
from fruitfly_agent.lab.improvement.api import BudgetScope
from fruitfly_agent.lab.rsi.persistent import PersistentEvolutionDriver
from fruitfly_agent.lab.algorithms.evolution import VerificationEvidence, AdoptionResult


class Host:
    def __init__(self, budget):
        self.budget, self.job, self.active = budget, None, 'version-0'
        self.proposals = 0
        self.crash_ready = False
        self.crash_propose = False
        self.active_candidate = ''
    def active_manifest(self): return self.active
    def load_job(self, identity): return self.job
    def save_job(self, job):
        if self.crash_ready and job.phase == 'ready' and job.steps == 1:
            raise RuntimeError('crash after activation')
        self.job = job
    async def propose(self, direction):
        self.proposals += 1
        self.budget.reserve('model', 2)
        self.budget.reserve('execution')
        if self.crash_propose: raise RuntimeError('unknown paid result')
        return 'candidate-' + str(self.proposals)
    async def verify(self, candidate, policy):
        return VerificationEvidence(candidate, 'artifact', self.active, policy, True)
    async def adopt(self, candidate, evidence):
        self.active = 'version-' + str(self.proposals)
        self.active_candidate = candidate
        return AdoptionResult('activated', self.active)
    def is_active(self, candidate): return self.active_candidate == candidate


class DurableBudgetTests(unittest.IsolatedAsyncioTestCase):
    async def test_activation_recovery_restores_spent_quota_before_next_generation(self):
        host = Host(BudgetScope({'model': 10, 'execution': 5})); host.crash_ready = True
        driver = PersistentEvolutionDriver()
        with self.assertRaisesRegex(RuntimeError, 'crash after activation'):
            await driver.evolve(host, job_id='job', policy_id='policy', direction='improve', max_steps=2)
        self.assertEqual(host.job.phase, 'activating')
        host.budget = BudgetScope({'model': 10, 'execution': 5}); host.crash_ready = False
        result = await driver.evolve(host, job_id='job', policy_id='policy', direction='improve', max_steps=2)
        self.assertEqual(result.phase, 'complete')
        self.assertEqual(host.proposals, 2)
        self.assertEqual(host.budget.used, {'model': 4, 'execution': 2})
        self.assertEqual(result.budget_state['used'], host.budget.used)

    async def test_unknown_paid_phase_is_not_replayed_or_refunded(self):
        host = Host(BudgetScope({'model': 5, 'execution': 3})); host.crash_propose = True
        driver = PersistentEvolutionDriver()
        with self.assertRaisesRegex(RuntimeError, 'unknown paid result'):
            await driver.evolve(host, job_id='job', policy_id='policy', direction='improve')
        host.budget = BudgetScope({'model': 5, 'execution': 3}); host.crash_propose = False
        result = await driver.evolve(host, job_id='job', policy_id='policy', direction='improve')
        self.assertEqual(result.phase, 'interrupted')
        self.assertEqual(result.stop_reason, 'interrupted_usage_unknown')
        self.assertEqual(host.budget.used, host.budget.limits)
        self.assertEqual(host.proposals, 1)

    async def test_changed_root_limits_reject_resume_and_exhaustion_stops_before_proposal(self):
        host = Host(BudgetScope({'model': 4, 'execution': 2}))
        driver = PersistentEvolutionDriver()
        result = await driver.evolve(host, job_id='job', policy_id='policy', direction='improve', max_steps=5)
        self.assertEqual((result.steps, result.stop_reason), (2, 'budget_exhausted'))
        self.assertEqual(host.proposals, 2)
        host.budget = BudgetScope({'model': 8, 'execution': 2})
        with self.assertRaisesRegex(ValueError, 'strategy'):
            await driver.evolve(host, job_id='job', policy_id='policy', direction='improve', max_steps=5)
