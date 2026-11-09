"""Optional benchmark adapters use real stage contracts without Docker or models."""
from tests.support.configuration import component_parameters, with_component_parameters, with_component_text, component_text
from fruitfly_eval.installation import installation_identity
from tests.support.configuration import profile_document
import asyncio
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import yaml

from fruitfly_eval.improvement import benchmark_execution
from fruitfly_eval.improvement.runner import EvalTaskRunner
from fruitfly_agent.lab.improvement.components import ComponentRegistry, TextComponentAdapter
from fruitfly_agent.improvement.contracts.plans import RunPlan
from fruitfly_agent.improvement.stages.services import StageServices
from fruitfly_agent.lab.improvement.editor.generators import GeneratorRegistry
from fruitfly_agent.lab.improvement.execution import ExecutionContext
from fruitfly_agent.improvement.contracts.experiments import ExecutionRequest
from fruitfly_agent.improvement.contracts.tasks import TaskMaterial
from fruitfly_agent.improvement.contracts.candidates import CandidateBundle, EditReason
from fruitfly_agent.improvement.contracts.components import ComponentFile, HarnessSnapshot
from fruitfly_agent.improvement.contracts.editing import ProposalResult
from fruitfly_agent.improvement.contracts.assessment import SelectionDecision
from fruitfly_agent.lab.base_prompt.target import BasePromptTarget
from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts
from tests.support.stages import version


class BenchmarkImprovementTests(unittest.IsolatedAsyncioTestCase):
    def fixture(self, root):
        artifacts = MemoryArtifacts()
        components = ComponentRegistry((TextComponentAdapter(BasePromptTarget('baseline'), 'system-prompt'),))
        (root / '.fruitfly').mkdir()
        (root / '.fruitfly/config.yaml').write_text(yaml.safe_dump({'default_profile': 'default',
            'profiles': {'default': profile_document(catalog='models.yaml', executor='test', mechanisms=[])}}))
        (root / '.fruitfly/models.yaml').write_text('models: {}\n')
        request = root / 'request.json'
        request.write_text(json.dumps({'runtime': {'working_directory': str(root),
            'config_path': '.fruitfly/config.yaml'}, 'benchmark': {'id': 'terminal-bench-4', 'variant': 'smoke'},
            'execution': {'attempts': 1, 'concurrency': 1, 'timeout_seconds': 300}}))
        host = root / 'host.yaml'; host.write_text('prepared host identity')
        task = root / 'task'; task.mkdir(); (task / 'instruction.md').write_text('Complete an external task.')
        source = Path(__file__).resolve().parents[2]
        files = installation_identity(source)['files']
        receipt = {'id': 'prepared-identity', 'runtime': {'installation': {'files': files}},
            'tasks': [{'id': 'external/task', 'path': str(task)}]}
        plan = RunPlan('experiment', version(), ('base_prompt',), generator_id='rule')
        services = StageServices(plan)
        context = ExecutionContext(root, artifacts, components, None, None, None, plan=plan, services=services)
        return context, request, host, receipt

    def freeze(self, context, request, host, receipt, executor):
        definition = benchmark_execution(request, host,  executor=executor)
        host_model = SimpleNamespace(agent_env={'FRUITFLY_MAX_MODEL_CALLS': '2'})
        return definition, patch('fruitfly_eval.improvement.registration.HostConfig.read', return_value=host_model), patch(
            'fruitfly_eval.improvement.registration.load_preparation', return_value=receipt)


    async def test_preview_is_offline_and_changed_model_material_invalidates_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); context, request, host, receipt = self.fixture(root)
            async def forbidden(*args, **kwargs): self.fail('preview executed an external task')
            definition, host_patch, receipt_patch = self.freeze(context, request, host, receipt, forbidden)
            with host_patch, receipt_patch:
                self.assertFalse(definition.materials(context)[0].error)
                prepared = definition.prepare(context, ExecutionRequest('', (), ('base_prompt',), 'benchmark-task', 'task'))
                (root / '.fruitfly/models.yaml').write_text('changed')
                self.assertNotEqual(prepared.current_source(), prepared.source_id)
                self.assertEqual(context.services.used['model'], 0)
            await context.services.close()

    async def test_cancelled_external_work_keeps_conservative_allowance_and_closes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); context, request, host, receipt = self.fixture(root)
            entered, cleaned = asyncio.Event(), asyncio.Event()
            async def executor(*args, **kwargs):
                entered.set()
                try: await asyncio.Event().wait()
                finally: cleaned.set()
            definition, host_patch, receipt_patch = self.freeze(context, request, host, receipt, executor)
            with host_patch, receipt_patch:
                prepared = definition.prepare(context, ExecutionRequest('', (), ('base_prompt',), 'benchmark-task', 'task'))
                runner = definition.build(context, prepared).runner
                pending = asyncio.create_task(runner.execute(context.plan, prepared.task, context.components.snapshot()))
                await entered.wait(); pending.cancel()
                with self.assertRaises(asyncio.CancelledError): await pending
                self.assertTrue(cleaned.is_set())
                self.assertEqual(context.services.used['model'], 0)
                self.assertFalse(hasattr(context.services,'budget'))
                settlements = [f for e, f in context.services.events if e == 'external-usage']
                self.assertIsNone(settlements[-1]['observed_calls'])
            await context.services.close()

    async def test_old_prepared_runtime_is_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); context, request, host, receipt = self.fixture(root)
            receipt['runtime']['installation']['files'] = []
            definition, host_patch, receipt_patch = self.freeze(context, request, host, receipt, None)
            with host_patch, receipt_patch:
                self.assertIn('prepare', definition.materials(context)[0].error)
            await context.services.close()

    async def test_pre_budget_runtime_without_configured_limits_is_rejected_offline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); context, request, host, receipt = self.fixture(root)
            receipt['runtime']['installation']['files'] = [
                pair for pair in receipt['runtime']['installation']['files']
                if pair[0] != 'fruitfly_agent/run/configuration/profile.py']
            definition, host_patch, receipt_patch = self.freeze(context, request, host, receipt, None)
            with host_patch, receipt_patch:
                self.assertIn('execution limits or facts', definition.materials(context)[0].error)
                self.assertEqual(context.services.used, {'model': 0, 'execution': 0})
            await context.services.close()


    async def test_timeout_collects_partial_evidence_and_observed_usage(self):
        from fruitfly_agent.improvement.stages.operations import run_stage
        from fruitfly_agent.improvement.contracts.failures import StageFailure
        from fruitfly_agent.improvement.execution.facts import read_facts
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); context, request, host, receipt = self.fixture(root)
            class Interrupted:
                result_root = root / 'partial'
                async def __call__(self, *args, **kwargs):
                    agent = self.result_root / 'artifacts/harbor/job/trial/agent'; agent.mkdir(parents=True)
                    (agent / 'model-usage.json').write_text('{"schema_version":1,"used":1,"requests":[{"id":"call-0","status":"completed","usage":null}]}')
                    (agent / 'session.jsonl').write_text('{"type":"message","message":{"role":"toolResult","content":[]}}\n')
                    await asyncio.Event().wait()
            definition, host_patch, receipt_patch = self.freeze(context, request, host, receipt, Interrupted())
            context.plan = replace(context.plan, timeouts={'editor_seconds':.01,'execution_seconds':.01,'evaluator_seconds':.01})
            context.services = StageServices(context.plan)
            with host_patch, receipt_patch:
                prepared = definition.prepare(context, ExecutionRequest('', (), ('base_prompt',), 'benchmark-task', 'task'))
                runner = definition.build(context, prepared).runner
                with self.assertRaises(StageFailure) as caught:
                    await run_stage(context.services, 'execute', runner.execute(context.plan, prepared.task, context.components.snapshot()))
                record = caught.exception.record
                self.assertIsNotNone(record)
                self.assertEqual(record.model_calls, 1)
                self.assertEqual(record.status, 'cancelled')
                self.assertTrue(read_facts(record, context.artifacts).diagnosable)
                self.assertEqual(context.services.used['model'], 1)
            await context.services.close()

    async def test_interrupted_partial_json_does_not_discard_original_evidence_or_invent_usage(self):
        from fruitfly_eval.improvement.evidence import collect
        from fruitfly_eval.improvement.facts import attach_benchmark_facts
        from fruitfly_agent.improvement.execution.facts import read_facts
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            agent = root / 'artifacts/harbor/job/trial/agent'; agent.mkdir(parents=True)
            (agent / 'session.jsonl').write_bytes(b'{"message":{"role":"toolResult"}}\n{"message":')
            (agent / 'model-usage.json').write_text('{"schema_version":1,"used":')
            artifacts = MemoryArtifacts()
            resources, calls = collect(root, artifacts, interrupted=True)
            self.assertIsNone(calls)
            self.assertTrue(any(r.path.endswith('reading-trajectory.jsonl') for r in resources))
            scope = json.loads(artifacts.read(next(r.artifact_id for r in resources if r.path == 'diagnostics/reading-scope.json')))
            self.assertTrue(scope['gaps'])
            task = TaskMaterial('task', 'Work')
            plan = RunPlan('partial', version(), ('base_prompt',))
            from fruitfly_agent.improvement.contracts.execution import ExecutionRecord
            record = ExecutionRecord('run', task.task_id, task.material_id, plan.parent.harness,
                plan.parent.state, plan.conditions_id, 'cancelled', '', resources, calls)
            record = attach_benchmark_facts(record, root, artifacts,  interrupted=True)
            facts = read_facts(record, artifacts)
            self.assertTrue(facts.diagnosable)
            self.assertFalse(facts.complete)
            with self.assertRaises(ValueError): collect(root, artifacts)
            (agent / 'model-usage.json').write_text('{"schema_version":1,"used":1,"requests":[{}]}')
            resources, calls = collect(root, artifacts, interrupted=True)
            self.assertIsNone(calls)
            self.assertTrue(any(r.path.endswith('reading-trajectory.jsonl') for r in resources))
