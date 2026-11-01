"""Improvement mechanisms behavior and failure contracts."""
from dataclasses import replace
import json
from types import SimpleNamespace
import unittest
from fruitfly_agent.improvement.workflow.services import WorkflowServices
from fruitfly_agent.improvement.contracts.tasks import TaskMaterial
from fruitfly_agent.lab.improvement.execution import ExecutionContext
from fruitfly_agent.improvement.contracts.editing import ProposalRequest
from fruitfly_agent.lab.improvement.editor import AgentEditor
from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts, EvidenceWorkspace
from fruitfly_agent.lab.improvement.evidence.access import EvidenceAccess
from fruitfly_agent.lab.improvement.evidence.rounds import RoundIndex
from fruitfly_agent.lab.improvement.evidence.configuration import EvidenceSettings
from fruitfly_agent.lab.improvement.workflow.mechanisms import install_workflow_mechanisms
from fruitfly_agent.core.config import AgentLoopConfig
from tests.support.pipeline import build_pipeline, RuleGenerator
from tests.support.faux_provider import FauxProvider


class KernelTests(unittest.IsolatedAsyncioTestCase):
    async def test_sync_faults_bad_results_and_stop_fault_preserve_prior_executions(self):
        for target in ('propose', 'execute', 'select', 'stop', 'assess'):
            with self.subTest(stage=target):
                flow, plan, baseline, runner = build_pipeline()
                plan = replace(plan,  rounds=2)
                def broken(*args, **kwargs):
                    raise RuntimeError('synchronous plugin failure')
                if target == 'propose':
                    generator = RuleGenerator(); generator.propose = broken
                    flow.generators.factories['rule-generator'] = lambda: generator
                elif target == 'execute':
                    original = runner.execute
                    def execute(plan, task, harness):
                        return original(plan, task, harness) if harness == baseline else object()
                    runner.execute = execute
                elif target == 'select':
                    flow.selector.select = lambda *a: object()
                elif target == 'stop':
                    flow.stop_policy = SimpleNamespace(decide=broken)
                elif target == 'explore':
                    flow.exploration = SimpleNamespace(choose=lambda *a: object())
                else:
                    flow.completed_assessment = SimpleNamespace(assess=broken, ensure_available=lambda: None)
                services = WorkflowServices(plan)
                try:
                    outcome = await flow.run(plan, TaskMaterial('task', 'Work'), baseline, services)
                    self.assertTrue(outcome.records)
                    self.assertIsNotNone(outcome.selected)
                    self.assertNotEqual(outcome.decision.assurance, 'verified')
                    self.assertTrue(any(e == 'stage-failed' for e, _ in services.events))
                finally:
                    await services.close()

    async def test_verification_refusal_still_emits_end_without_assurance(self):
        flow, plan, baseline, _ = build_pipeline()
        plan = replace(plan, purpose='persistent')
        async def refuse(outcome): return None
        flow.verifier = SimpleNamespace(verify=refuse)
        services, seen = WorkflowServices(plan), []
        services.hooks.register('before_run_end', lambda e: seen.append(json.loads(e.snapshot_json)))
        try:
            outcome = await flow.run(plan, TaskMaterial('task', 'Work'), baseline, services)
            self.assertEqual(outcome.stop_reason, 'verification_failed')
            self.assertIsNone(outcome.decision)
            self.assertEqual(seen[-1]['stop_reason'], 'verification_failed')
        finally:
            await services.close()

    async def test_research_context_reaches_generator_and_is_task_local(self):
        flow, plan, baseline, _ = build_pipeline()
        flow.artifacts = artifacts = MemoryArtifacts()
        generator = RuleGenerator()
        flow.generators.factories['rule-generator'] = lambda: generator
        services = WorkflowServices(plan)
        saved = []
        context = ExecutionContext('.', artifacts, flow.components, None, None, None,
            plan=plan, services=services, workflow_settings={},
            save_record=lambda path, value: saved.append((path, value)))
        flow.stop_policy = install_workflow_mechanisms(context)
        try:
            await flow.run(plan, TaskMaterial('task', 'Work'), baseline, services)
            request = generator.requests[0]
            self.assertEqual(request.context[0].path, 'rounds.json')
            value = json.loads(artifacts.read(request.context[0].artifact_id))
            self.assertTrue(value['links'])
            self.assertIn('run_id', value['links'][0])
            workspace = EvidenceWorkspace.build(request, artifacts)
            self.assertEqual(json.loads(workspace.read('context/extensions/rounds.json')), value)
            self.assertEqual(saved, [])
            other = RoundIndex(replace(context, services=WorkflowServices(plan)))
            self.assertEqual(json.loads(artifacts.read(other.before_proposal(type('Event', (), {'job_id': plan.job_id, 'round_index':0})()).resources[0].artifact_id))['links'], [])
            await other.context.services.close()
        finally:
            await services.close()

    async def test_workflow_observes_usage_without_hidden_reserves(self):
        flow, plan, baseline, runner = build_pipeline()
        plan = replace(plan)
        services = WorkflowServices(plan)
        context = ExecutionContext('.', MemoryArtifacts(), flow.components, None, None, None,
            plan=plan, services=services, workflow_settings={})
        flow.stop_policy = install_workflow_mechanisms(context)
        try:
            result = await flow.run(plan, TaskMaterial('task', 'Work'), baseline, services)
            self.assertIsNotNone(result.selected)
            self.assertEqual(services.used['execution'], 2)
            self.assertFalse(hasattr(services, 'budget'))
        finally:
            await services.close()

    async def test_missing_evidence_cannot_justify_changed_candidate_or_forge_supply(self):
        flow, plan, baseline, runner = build_pipeline()
        task = TaskMaterial('task', 'Work')
        record = await runner.execute(plan, task, baseline)
        artifacts, provider = MemoryArtifacts(), FauxProvider()
        for _ in range(2):
            provider.respond_tool_call('read', {'path': 'context/executions/' + record.run_id + '/missing.log'})
            provider.respond_tool_call('write_file', {'path': 'harness/prompt/instructions.txt', 'content': 'unsupported edit'})
            provider.respond_text(json.dumps({'reasons': [{'component_id': 'prompt', 'explanation': 'Unseen evidence', 'evidence_ids': [record.run_id], 'expected_effect':'The proposed behavior appears in the subsequent execution.'}]}))
        services = WorkflowServices(plan)
        try:
            editor = AgentEditor(AgentLoopConfig(provider=provider), artifacts, flow.components)
            with self.assertRaises(RuntimeError):
                await editor.edit('propose', ProposalRequest(plan, task, baseline, (record,), 'invariant', 0), services)
            self.assertTrue(any(e == 'editor-evidence-unavailable' for e, _ in services.events))
            access = EvidenceAccess((record.run_id,))
            access.provided('harness/prompt/fake.json', '{"run_id":"' + record.run_id + '"}')
            self.assertEqual(access.supplied, set())
        finally:
            await services.close()

    def test_fixed_evidence_settings_reject_unknown_and_invalid_limits(self):
        with self.assertRaises(ValueError): EvidenceSettings.from_dict({'research': {}})
        with self.assertRaises(ValueError): EvidenceSettings.from_dict({'read': {'default_characters': 25000}})
        with self.assertRaises(ValueError): EvidenceSettings.from_dict({'search': {'max_matches': True}})
