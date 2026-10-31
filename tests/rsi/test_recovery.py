"""Interrupted stages are not replayed; confirmed activation is reconciled."""
import unittest
from fruitfly_agent.rsi.engine import EvolutionEngine
from fruitfly_agent.rsi.contracts import VerificationEvidence,AdoptionResult,EvolutionJob


class Host:
    def __init__(self):
        self.job=None;self.active='version-0';self.proposals=0
        self.crash_ready=False;self.crash_propose=False;self.active_candidate=''
    def active_manifest(self):return self.active
    def load_job(self,identity):return self.job
    def save_job(self,job):
        if self.crash_ready and job.phase=='ready' and job.steps==1:raise RuntimeError('crash after activation')
        self.job=job
    async def propose(self,direction):
        self.proposals+=1
        if self.crash_propose:raise RuntimeError('unknown paid result')
        return 'candidate-'+str(self.proposals)
    async def verify(self,candidate,policy):return VerificationEvidence(candidate,'artifact',self.active,policy,True)
    async def adopt(self,candidate,evidence):
        self.active='version-'+str(self.proposals);self.active_candidate=candidate
        return AdoptionResult('activated',self.active)
    def is_active(self,candidate):return self.active_candidate==candidate


class DurableRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_confirmed_activation_is_reconciled_without_repeating_adoption(self):
        host=Host();host.crash_ready=True;driver=EvolutionEngine()
        with self.assertRaisesRegex(RuntimeError,'crash after activation'):
            await driver.evolve(host,job_id='job',policy_id='policy',direction='improve',max_steps=2)
        self.assertEqual(host.job.phase,'activating');host.crash_ready=False
        result=await driver.evolve(host,job_id='job',policy_id='policy',direction='improve',max_steps=2)
        self.assertEqual(result.phase,'complete');self.assertEqual(host.proposals,2)

    async def test_unknown_phase_is_not_replayed(self):
        host=Host();host.crash_propose=True;driver=EvolutionEngine()
        with self.assertRaisesRegex(RuntimeError,'unknown paid result'):
            await driver.evolve(host,job_id='job',policy_id='policy',direction='improve')
        host.crash_propose=False
        result=await driver.evolve(host,job_id='job',policy_id='policy',direction='improve')
        self.assertEqual((result.phase,result.stop_reason),('interrupted','interrupted_usage_unknown'))
        self.assertEqual(host.proposals,1)

    async def test_changed_conditions_and_retired_record_fields_reject(self):
        host=Host();driver=EvolutionEngine()
        await driver.evolve(host,job_id='job',policy_id='policy',direction='improve',max_steps=2)
        with self.assertRaisesRegex(ValueError,'parameters'):
            await driver.evolve(host,job_id='job',policy_id='policy',direction='improve',max_steps=3)
        with self.assertRaises(TypeError):EvolutionJob('job','policy','improve','manifest',budget_state={})
