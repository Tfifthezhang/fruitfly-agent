"""General stopping, independent scoring and versioned file changes."""
import asyncio
from dataclasses import replace
import unittest

from fruitfly_agent.lab.improvement.termination import AllOf, AnyOf, FailureLimit, IterationLimit, NoImprovement, ResourceLimit, ScoreAtLeast, StopDecision
from fruitfly_agent.lab.improvement.assessment.registry import AssessorRegistry
from fruitfly_agent.improvement.contracts.live import Assessment, EvidencePosition, Metric
from fruitfly_agent.lab.improvement.components.changes import ChangeSet, FileChange
from fruitfly_agent.lab.improvement.assessment.feedback import FeedbackProjection
from fruitfly_agent.lab.improvement.assessment.comparison import LexicographicComparison, Objective
from fruitfly_agent.lab.improvement.assessment.scorers.model import ModelAssessor
from fruitfly_agent.improvement.contracts.plans import RunPlan
from fruitfly_agent.improvement.contracts.stopping import SearchState
from fruitfly_agent.improvement.contracts.tasks import TaskMaterial
from fruitfly_agent.lab.improvement.assessment.aggregation import WeightedSum
from fruitfly_agent.improvement.workflow.services import WorkflowServices
from fruitfly_agent.improvement.contracts.versions import content_hash
from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts
from fruitfly_agent.improvement.workflow.budget import BudgetScope
from fruitfly_agent.rsi import AgentVersion, Candidate, EvolutionBudget, EvolutionDriver, Verification
from fruitfly_agent.rsi.engine import EvolutionEngine
from fruitfly_agent.rsi.contracts import VerificationEvidence, AdoptionResult
from fruitfly_agent.core.config import AgentLoopConfig
from tests.support.faux_provider import FauxProvider
from tests.support.pipeline import fixture, version


class EvolutionPolicyTests(unittest.IsolatedAsyncioTestCase):
    async def test_online_judge_rejects_an_intermediate_json_answer(self):
        from fruitfly_agent.core.data_model import AssistantMessage, TextBlock
        from fruitfly_agent.improvement.contracts.live import ExecutionEvent
        provider = FauxProvider()
        provider.respond(AssistantMessage([TextBlock('{"metrics":[]}')], stop_reason='stop', continue_turn=True))
        services = WorkflowServices(RunPlan('judge-intermediate', version(), ('prompt',)))
        judge = ModelAssessor('judge', config=AgentLoopConfig(provider=provider), services=services,
            instruction='Assess.', render=lambda event: event.kind)
        _, baseline = fixture()
        try:
            with self.assertRaisesRegex(ValueError, 'tool-free judgment'):
                await judge.assess(ExecutionEvent(EvidencePosition('run', baseline.snapshot_id, 'initial', 1), 'finished'))
            self.assertEqual(services.used['model'], 1)
        finally:
            await services.close()

    async def test_rejected_candidates_continue_and_configured_patience_stops(self):
        start = AgentVersion('task:0', 'editor:0')
        seen = []
        async def propose(parent, feedback, *, signal):
            seen.append(feedback)
            return Candidate(parent, AgentVersion('task:' + str(len(seen)), 'editor:0'))
        async def reject(candidate, *, signal): return Verification(candidate.version, 'quality', False, 'not improved')
        async def adopt(*args, **kwargs): self.fail('rejected candidate reached adoption')
        driver = EvolutionDriver(generator_for=lambda _: propose, verify=reject, adopt=adopt, policy_id='quality',
            budget=EvolutionBudget(max_steps=8), stop_policy=NoImprovement(2))
        result = await driver.evolve(start)
        self.assertEqual(len(seen), 2)
        self.assertEqual(seen[1], 'not improved')
        self.assertEqual(result.stop_reason, 'no_improvement')
        self.assertEqual(result.version, start)

    async def test_verified_goal_stops_after_actual_adoption(self):
        start = AgentVersion('task:0', 'editor:0')
        async def propose(parent, feedback, *, signal): return Candidate(parent, AgentVersion('task:1', 'editor:1'))
        async def verify(candidate, *, signal): return Verification(candidate.version, 'quality', True, score=1)
        async def adopt(candidate, verification, *, signal): return True
        result = await EvolutionDriver(generator_for=lambda _: propose, verify=verify, adopt=adopt,
            policy_id='quality', stop_policy=ScoreAtLeast('quality', 1), budget=EvolutionBudget(max_steps=5)).evolve(start)
        self.assertEqual(result.stop_reason, 'goal_reached')
        self.assertEqual(len(result.attempts), 1)
        self.assertEqual(result.version.improver_artifact, 'editor:1')

    async def test_durable_rejection_can_continue_and_strategy_changes_reject(self):
        class Host:
            def __init__(self): self.job = None; self.proposals = 0
            def active_manifest(self): return 'manifest'
            def load_job(self, job_id): return self.job
            def save_job(self, job): self.job = job
            async def propose(self, direction): self.proposals += 1; return 'candidate-' + str(self.proposals)
            async def verify(self, candidate, policy): return VerificationEvidence(candidate, 'artifact', 'manifest', policy, False)
            async def adopt(self, *args): raise AssertionError('cannot adopt a rejection')
        host = Host()
        result = await EvolutionEngine().evolve(host, job_id='job', policy_id='policy', direction='improve',
            max_steps=5, continue_on_rejection=True, stop_policy=NoImprovement(2))
        self.assertEqual((result.phase, result.steps, result.stop_reason), ('complete', 2, 'no_improvement'))
        self.assertEqual(result.consecutive_no_gain, 2)
        with self.assertRaisesRegex(ValueError, 'strategy'):
            await EvolutionEngine().evolve(host, job_id='job', policy_id='policy', direction='improve', max_steps=5)

    async def test_external_settlement_charges_held_quota_even_after_cancellation(self):
        root = BudgetScope({'model': 10, 'execution': 2})
        child = root.child({'model': 7, 'execution': 0})
        self.assertEqual(root.available('model'), 3)
        root.signal.set()
        child.settle('model', 4)
        child.close()
        self.assertEqual(root.used['model'], 4)
        self.assertEqual(root.held['model'], 0)
        root.signal.clear()
        self.assertEqual(root.available('model'), 6)

    async def test_model_judge_has_its_own_configuration_and_shared_budget(self):
        artifacts = MemoryArtifacts()
        _, baseline = fixture()
        provider = FauxProvider(); provider.respond_text('{"metrics":[{"name":"quality","value":0.8}]}')
        plan = RunPlan('judge-job', version(), ('prompt',))
        services = WorkflowServices(plan)
        judge = ModelAssessor('judge-v1', config=AgentLoopConfig(provider=provider, model='judge-model'),
            services=services, instruction='Assess the supplied evidence.', render=lambda event: event.kind)
        from fruitfly_agent.improvement.contracts.live import ExecutionEvent
        value = await judge.assess(ExecutionEvent(EvidencePosition('run', baseline.snapshot_id, 'initial', 1), 'finished'))
        self.assertEqual(value.metrics[0].value, 0.8)
        self.assertEqual(services.used['model'], 1)
        self.assertEqual(provider.calls[0]['tools'], [])
        self.assertEqual(provider.calls[0]['model'], 'judge-model')
        await services.close()

    def test_multi_metric_comparison_unknown_values_and_private_feedback(self):
        _, baseline = fixture()
        p = EvidencePosition('run', baseline.snapshot_id, 'initial', 1)
        a = Assessment(p, 'judge', (Metric('quality', 0.5), Metric('cost', 10)), status='final', scope='execution')
        b = replace(a, metrics=(Metric('quality', 0.5), Metric('cost', 5)))
        compare = LexicographicComparison((Objective('quality'), Objective('cost', 'min')))
        self.assertEqual(compare.compare(a, b), 'better')
        self.assertEqual(compare.compare(a, replace(b, status='provisional')), 'insufficient')
        self.assertIsNone(WeightedSum({'missing': 1}).aggregate(a).value)
        self.assertIsNone(FeedbackProjection(('quality',)).project(replace(a, visibility='private')))
        self.assertEqual([m.name for m in FeedbackProjection(('quality',)).project(a).metrics], ['quality'])
        state = SearchState(2, 5, 1, False, False, consecutive_no_gain=2)
        self.assertIsNotNone(AllOf(IterationLimit(3), NoImprovement(2)).decide(state))
        self.assertEqual(AnyOf(NoImprovement(2), IterationLimit(1)).decide(state).reason, 'no_improvement')

    def test_file_changes_bind_parent_and_content_without_claiming_code_activation(self):
        _, baseline = fixture()
        artifacts = MemoryArtifacts()
        document = baseline.component('prompt')
        body = artifacts.put(b'new instructions')
        extra = artifacts.put(b'def helper():\n    return 1\n')
        change = ChangeSet(document.component_id, document.document_id, (
            FileChange('instructions.txt', content_hash(document.files[0].text), body),
            FileChange('helpers.py', None, extra)))
        after = change.apply(document, artifacts)
        self.assertEqual({f.path for f in after.files}, {'instructions.txt', 'helpers.py'})
        with self.assertRaisesRegex(ValueError, 'parent'):
            change.apply(after, artifacts)
