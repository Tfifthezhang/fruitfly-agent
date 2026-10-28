"""Sparse rewards, completed assessment and exploration remain separate decisions."""
from dataclasses import asdict, replace
import asyncio
import json
import unittest

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.data_model import AssistantMessage, TextBlock
from fruitfly_agent.core.model_stream import AssistantMessageEventStream, StreamDone
from fruitfly_agent.lab.improvement.api import (CandidateBundle, ComponentFile, ComponentWorkflow,
    EditReason, GeneratorRegistry, HarnessSnapshot, Measurement, ProposalResult, RunPlan, TaskMaterial,
    WorkflowServices, ProcessAssessmentSettings, CompletedAssessmentService, builtin_completed_assessors,
    builtin_explorations, ensure_facts, read_facts, receipt_facts, attach_facts, Resource, ArtifactFact,
    MetricThreshold, FailureLimit, CompletedAssessorRegistry, CompletedAssessorDefinition,
    ExplorationRegistry, ExplorationDefinition)
from fruitfly_agent.improvement.contracts.versions import content_hash
from fruitfly_agent.lab.improvement.evidence import EvidenceWorkspace, MemoryArtifacts
from tests.support.faux_provider import FauxProvider
from tests.support.pipeline import fixture, version, Runner


class Increment:
    generator_id = 'increment'
    required_capabilities = frozenset()

    def __init__(self): self.requests = []

    async def propose(self, request, services):
        self.requests.append(request)
        document = request.baseline.component('prompt')
        changed = replace(document, files=(ComponentFile('instructions.txt', document.files[0].text + '+'),))
        snapshot = HarnessSnapshot(tuple(changed if c.component_id == 'prompt' else c for c in request.baseline.components))
        return ProposalResult((CandidateBundle(request.plan.parent, request.baseline, snapshot, self.generator_id,
            (EditReason('prompt', 'Synthetic observed hypothesis', (request.records[-1].run_id,)),)),))


class ZeroReward:
    async def measure(self, task, record): return Measurement(record.run_id, 'official', 0)


def judge_response(view, signal=None):
    payload = json.loads(view.messages[0].content)
    if 'incumbent' in payload:
        chosen = payload['executions'][-1]
        response = {'run_id': chosen['facts']['run_id'], 'reason': 'Synthetic exploration judgment, not adoption.',
            'evidence_ids': [chosen['facts_id']]}
    else:
        chosen = payload['executions'][0]
        response = {'metrics': [], 'detail': 'Synthetic completed judgment with no success claim.',
            'evidence_ids': [chosen['facts_id']]}
    async def stream():
        yield StreamDone(AssistantMessage(content=[TextBlock(json.dumps(response))], stop_reason='stop'))
    return AssistantMessageEventStream(stream())


class CompletedImprovementTests(unittest.IsolatedAsyncioTestCase):
    async def test_intermediate_response_cannot_be_used_as_completed_judgment(self):
        _, _, _, services, assessment, _, _, provider = self.prepare()
        provider.script = []
        provider.respond(AssistantMessage([TextBlock('{"metrics": []}')], stop_reason='stop', continue_turn=True))
        try:
            with self.assertRaisesRegex(ValueError, 'final result'):
                await assessment.complete('Assess.', {})
            self.assertEqual(services.used['model'], 1)
        finally:
            await services.close()
    def prepare(self, *, required=False, calls=16, invalid=False, root_calls=64, rounds=2, stop=None):
        components, baseline = fixture()
        artifacts = MemoryArtifacts()
        provider = FauxProvider()
        if invalid:
            for _ in range(8): provider.respond_text('not valid JSON')
        else:
            provider.script = [judge_response] * 8
        config = AgentLoopConfig(provider=provider, model='separate-assessor')
        plan = RunPlan('completed', version(), ('prompt',), generator_id='increment', strategy_id='simple',
            depth=rounds, feedback='scored', retain_experience=False, max_model_calls=root_calls)
        services = WorkflowServices(plan)
        assessment = CompletedAssessmentService(ProcessAssessmentSettings(('completed-model-v1',), calls, 1, required),
            config=config, artifacts=artifacts, services=services, registry=builtin_completed_assessors())
        generator = Increment()
        generators = GeneratorRegistry(); generators.register('increment', lambda: generator)
        runner = Runner()
        flow = ComponentWorkflow(generators=generators, components=components, runner=runner, composer=None,
            selector=None, measurements=ZeroReward(), artifacts=artifacts, completed_assessment=assessment,
            exploration=builtin_explorations().get('process-guided').factory(), stop_policy=stop)
        return flow, plan, baseline, services, assessment, generator, artifacts, provider

    async def test_all_zero_rewards_keep_official_baseline_but_next_proposal_uses_exploration_seed(self):
        flow, plan, baseline, services, assessment, generator, artifacts, provider = self.prepare()
        try:
            outcome = await flow.run(plan, TaskMaterial('task', 'Complete a generic task.'), baseline, services)
            self.assertEqual(outcome.selected.run_id, 'run-1')
            self.assertEqual(outcome.harness, baseline)
            self.assertEqual(outcome.decision.assurance, 'selected')
            self.assertEqual(outcome.exploration[0].run_id, 'run-2')
            self.assertEqual(generator.requests[1].baseline.component('prompt').files[0].text, 'prompt+')
            self.assertEqual(outcome.candidates[1].harness.component('prompt').files[0].text, 'prompt++')
            workspace = EvidenceWorkspace.build(generator.requests[1], artifacts)
            self.assertIn('context/executions/run-2/execution-facts.json', workspace.paths())
            feedback = json.loads(workspace.read('context/executions/run-2/process-assessments.json'))
            self.assertEqual(feedback[0]['status'], 'final')
            self.assertEqual(len(provider.calls), 4)
            self.assertEqual(services.used, {'model': 4, 'execution': 3})
            self.assertTrue(all(call['tools'] == [] and call['model'] == 'separate-assessor' for call in provider.calls))
            comparison = json.loads(provider.calls[2]['messages'][0].content)
            self.assertTrue(comparison['executions'][0]['assessments'])
        finally:
            await services.close()

    async def test_optional_bad_judgments_fall_back_and_required_bad_judgments_stop_with_baseline(self):
        for required in (False, True):
            with self.subTest(required=required):
                flow, plan, baseline, services, assessment, generator, artifacts, provider = self.prepare(
                    invalid=True, required=required)
                try:
                    outcome = await flow.run(plan, TaskMaterial('task', 'Work.'), baseline, services)
                    self.assertEqual(outcome.selected.run_id, 'run-1')
                    self.assertEqual(outcome.stop_reason, 'assessment_unavailable' if required else 'repeated_candidates')
                    self.assertEqual(len(generator.requests), 0 if required else 2)
                    self.assertTrue(all(a.status == 'unavailable' for vs in assessment.values.values() for a in vs))
                finally:
                    await services.close()

    async def test_assessment_suballowance_does_not_reset_and_root_exhaustion_is_not_swallowed(self):
        for local, root, expected in ((1, 64, 'repeated_candidates'), (16, 1, 'budget_exhausted')):
            flow, plan, baseline, services, assessment, generator, artifacts, provider = self.prepare(calls=local, root_calls=root)
            try:
                result = await flow.run(plan, TaskMaterial('task', 'Work.'), baseline, services)
                self.assertEqual(result.stop_reason, expected)
                self.assertEqual(len(provider.calls), 1)
                self.assertEqual(services.used['model'], 1)
            finally:
                await services.close()

    async def test_final_process_assessments_reach_round_stopping(self):
        flow, plan, baseline, services, assessment, generator, artifacts, provider = self.prepare(rounds=3,
            stop=MetricThreshold('completed-model-v1', 'ready', 1))
        def ready(view, signal=None):
            payload = json.loads(view.messages[0].content)
            data = {'metrics': [{'name': 'ready', 'value': 1}], 'detail': 'Synthetic final metric.',
                'evidence_ids': [payload['executions'][0]['facts_id']]}
            async def stream(): yield StreamDone(AssistantMessage(content=[TextBlock(json.dumps(data))], stop_reason='stop'))
            return AssistantMessageEventStream(stream())
        provider.script = [ready] * 8
        try:
            result = await flow.run(plan, TaskMaterial('task', 'Work.'), baseline, services)
            self.assertEqual(result.stop_reason, 'metric_threshold')
            self.assertEqual(len(result.records), 2)
            self.assertEqual(result.exploration, ())
        finally:
            await services.close()

    async def test_completed_zero_score_is_not_a_failure_but_execution_errors_are_counted(self):
        flow, plan, baseline, services, assessment, generator, artifacts, provider = self.prepare(rounds=3, stop=FailureLimit(1))
        original = flow.runner.execute
        async def execute(plan, task, harness):
            record = await original(plan, task, harness)
            return replace(record, status='error') if record.run_id != 'run-1' else record
        flow.runner.execute = execute
        try:
            result = await flow.run(plan, TaskMaterial('task', 'Work.'), baseline, services)
            self.assertEqual(result.stop_reason, 'failure_limit')
            self.assertEqual(len(result.records), 2)
            self.assertEqual(result.selected.run_id, 'run-1')
        finally:
            await services.close()

    async def test_forged_evidence_cannot_expose_an_ungranted_artifact(self):
        flow, plan, baseline, services, assessment, generator, artifacts, provider = self.prepare()
        try:
            record = await flow.runner.execute(plan, TaskMaterial('task', 'Work.'), baseline)
            private = artifacts.put(b'PRIVATE CHECK ANSWER')
            facts = receipt_facts(record, artifacts)
            forged = replace(facts, evidence=(Resource('private.txt', private),))
            record = attach_facts(record, forged, artifacts)
            with self.assertRaisesRegex(ValueError, 'outside'):
                read_facts(record, artifacts)
            self.assertEqual(provider.calls, [])
        finally:
            await services.close()

    async def test_model_streams_close_on_completion_timeout_and_cancellation(self):
        for mode in ('complete', 'timeout', 'cancel'):
            with self.subTest(mode=mode):
                flow, plan, baseline, services, assessment, generator, artifacts, provider = self.prepare(required=True)
                entered, cleaned = asyncio.Event(), asyncio.Event()
                def response(view, signal=None):
                    async def events():
                        try:
                            entered.set()
                            if mode != 'complete':
                                await asyncio.Event().wait()
                            payload = json.loads(view.messages[0].content)
                            data = payload['executions'][-1]
                            body = ({'run_id': data['facts']['run_id'], 'reason': 'A synthetic next seed.',
                                     'evidence_ids': [data['facts_id']]} if 'incumbent' in payload else
                                    {'metrics': [], 'detail': 'A cited synthetic assessment.',
                                     'evidence_ids': [data['facts_id']]})
                            yield StreamDone(AssistantMessage(content=[TextBlock(json.dumps(body))], stop_reason='stop'))
                        finally:
                            cleaned.set()
                    return AssistantMessageEventStream(events())
                assessment.config = replace(assessment.config, provider=response)
                assessment.settings = replace(assessment.settings, timeout_seconds=0.05)
                pending = asyncio.create_task(flow.run(plan, TaskMaterial('task', 'Work.'), baseline, services))
                try:
                    await asyncio.wait_for(entered.wait(), 1)
                    if mode == 'cancel':
                        pending.cancel()
                        with self.assertRaises(asyncio.CancelledError):
                            await pending
                    else:
                        outcome = await pending
                        self.assertEqual(outcome.stop_reason, 'assessment_unavailable' if mode == 'timeout' else 'completed')
                    self.assertTrue(cleaned.is_set())
                    self.assertEqual(services.used['model'], 1 if mode != 'complete' else 4)
                finally:
                    pending.cancel()
                    await asyncio.gather(pending, return_exceptions=True)
                    await services.close()

    async def test_invalid_factory_products_are_owned_before_contract_validation(self):
        _, plan, _, services, _, _, artifacts, _ = self.prepare()
        closed = []
        class Invalid:
            assessor_id = 'incorrect-id'
            async def aclose(self): closed.append(self)
        assessor = Invalid()
        policy = Invalid()
        registry = CompletedAssessorRegistry((CompletedAssessorDefinition('custom', 'custom-v1', lambda service: assessor),))
        exploration = ExplorationRegistry((ExplorationDefinition('custom', 'custom-v1', lambda: policy),))
        try:
            with self.assertRaises(ValueError):
                registry.create('custom', None, own=services.own)
            with self.assertRaises(ValueError):
                exploration.create('custom', own=services.own)
        finally:
            await services.close()
        self.assertEqual(closed, [policy, assessor])
