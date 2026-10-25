"""Optional benchmark adapters use real stage contracts without Docker or models."""
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

from eval.improvement import benchmark_execution
from eval.improvement.runner import EvalTaskRunner
from fruitfly_agent.lab.improvement.api import (ComponentRegistry, TextComponentAdapter, RunPlan, WorkflowServices,
    ExecutionContext, ExecutionRequest, TaskMaterial, CandidateBundle, ComponentFile, HarnessSnapshot, EditReason,
    ComponentWorkflow, GeneratorRegistry, ProposalResult, SelectionDecision)
from fruitfly_agent.lab.base_prompt.target import BasePromptTarget
from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts
from tests.support.pipeline import version


class BenchmarkImprovementTests(unittest.IsolatedAsyncioTestCase):
    def fixture(self, root):
        artifacts = MemoryArtifacts()
        components = ComponentRegistry((TextComponentAdapter(BasePromptTarget('baseline'), 'system-prompt'),))
        (root / '.fruitfly').mkdir()
        (root / '.fruitfly/config.yaml').write_text(yaml.safe_dump({'schema_version': 1, 'default_profile': 'default',
            'profiles': {'default': {'model': {'catalog': 'models.yaml', 'profile': 'test'}, 'mechanisms': []}}}))
        (root / '.fruitfly/models.yaml').write_text('models: {}\n')
        request = root / 'request.json'
        request.write_text(json.dumps({'schema_version': 2, 'runtime': {'working_directory': str(root),
            'config_path': '.fruitfly/config.yaml'}, 'benchmark': {'id': 'terminal-bench-4', 'variant': 'smoke'},
            'execution': {'attempts': 1, 'concurrency': 1, 'timeout_seconds': 300}}))
        host = root / 'host.yaml'; host.write_text('prepared host identity')
        task = root / 'task'; task.mkdir(); (task / 'instruction.md').write_text('Complete an external task.')
        source = Path(__file__).resolve().parents[2]
        files = [(name, hashlib.sha256((source / name).read_bytes()).hexdigest()) for name in
            ('fruitfly_agent/run/runtime/limits.py', 'fruitfly_agent/run/cli.py', 'eval/harbor_agent.py',
             'fruitfly_agent/core/loop.py', 'fruitfly_agent/run/configuration/profile.py',
             'fruitfly_agent/run/runtime/assembly.py', 'fruitfly_agent/runtime_spec/execution.py',
             'fruitfly_agent/runtime_spec/profiles.py', 'fruitfly_agent/runtime_spec/selections.py', 'eval/runtime.py')]
        receipt = {'id': 'prepared-identity', 'runtime': {'installation': {'files': files}},
            'tasks': [{'id': 'external/task', 'path': str(task)}]}
        plan = RunPlan('experiment', version(), ('base_prompt',), generator_id='rule', feedback='scored', max_model_calls=100)
        services = WorkflowServices(plan)
        context = ExecutionContext(root, artifacts, components, None, None, None, plan=plan, services=services)
        return context, request, host, receipt

    def freeze(self, context, request, host, receipt, executor):
        definition = benchmark_execution(request, host, model_calls=2, executor=executor)
        host_model = SimpleNamespace(agent_env={'FRUITFLY_MAX_MODEL_CALLS': '2'})
        return definition, patch('eval.improvement.registration.HostConfig.read', return_value=host_model), patch(
            'eval.improvement.registration.load_preparation', return_value=receipt)

    async def test_candidate_executes_then_official_results_drive_existing_workflow(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            context, request, host, receipt = self.fixture(root)
            calls = []
            async def executor(evaluation, host_path, *, directory, output_root, emit):
                self.assertGreaterEqual(context.services.budget.held['model'], 2)
                data = yaml.safe_load(Path(evaluation.runtime.config_path).read_text())
                prompt = data['profiles']['default']['prompt']
                candidate = (root / '.fruitfly/artifacts' / prompt[7:]).read_text() != 'baseline'
                calls.append(candidate)
                path = output_root / ('evaluation-' + str(len(calls)))
                agent = path / 'artifacts/harbor/job/trial/agent'; agent.mkdir(parents=True)
                (agent / 'session.jsonl').write_text('{"type":"message"}\n')
                (agent / 'trajectory.json').write_text('{}')
                (agent / 'model-budget.json').write_text('{"schema_version":1,"limit":2,"used":2}')
                verifier = agent.parent / 'verifier'; verifier.mkdir(); (verifier / 'answers.txt').write_text('PRIVATE')
                emit('benchmark-progress', event_type='completed')
                return {'evaluation_id': path.name, 'status': 'completed', 'errors': {},
                    'metrics': [{'name': 'official_reward', 'value': float(candidate)}]}, path
            definition, host_patch, receipt_patch = self.freeze(context, request, host, receipt, executor)
            with host_patch, receipt_patch:
                prepared = definition.prepare(context, ExecutionRequest('', (), ('base_prompt',), 'benchmark-task', 'task', 'scored'))
                ports = definition.build(context, prepared)
                class Generator:
                    generator_id = 'rule'; required_capabilities = frozenset()
                    async def propose(self, request, services):
                        document = replace(request.baseline.components[0], files=(ComponentFile('instructions.txt', 'candidate'),))
                        candidate = CandidateBundle(request.plan.parent, request.baseline, HarnessSnapshot((document,)), 'rule',
                            (EditReason('base_prompt', 'Evidence-driven proposal', (request.records[0].run_id,)),))
                        return ProposalResult((candidate,))
                class Composer:
                    async def compose(self, request, services): return request.candidates[0]
                generators = GeneratorRegistry(); generators.register('rule', Generator)
                flow = ComponentWorkflow(generators=generators, components=context.components, runner=ports.runner,
                    composer=Composer(), selector=None, measurements=ports.measurements)
                result = await flow.run(context.plan, prepared.task, context.components.snapshot(), context.services)
                self.assertEqual(calls, [False, True, True, True])
                self.assertEqual(context.services.used, {'model': 8, 'execution': 4})
                self.assertEqual(result.harness.components[0].files[0].text, 'candidate')
                self.assertEqual(result.decision.assurance, 'selected')
                self.assertTrue(all('PRIVATE' not in context.artifacts.read(a.artifact_id).decode() for r in result.records for a in r.artifacts))
                self.assertTrue(all('reward' not in r.output for r in result.records))
                self.assertNotIn('prompt', yaml.safe_load((root / '.fruitfly/config.yaml').read_text())['profiles']['default'])
                await context.services.close()

    async def test_preview_is_offline_and_changed_model_material_invalidates_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); context, request, host, receipt = self.fixture(root)
            async def forbidden(*args, **kwargs): self.fail('preview executed an external task')
            definition, host_patch, receipt_patch = self.freeze(context, request, host, receipt, forbidden)
            with host_patch, receipt_patch:
                self.assertFalse(definition.materials(context)[0].error)
                prepared = definition.prepare(context, ExecutionRequest('', (), ('base_prompt',), 'benchmark-task', 'task', 'scored'))
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
                prepared = definition.prepare(context, ExecutionRequest('', (), ('base_prompt',), 'benchmark-task', 'task', 'scored'))
                runner = definition.build(context, prepared).runner
                pending = asyncio.create_task(runner.execute(context.plan, prepared.task, context.components.snapshot()))
                await entered.wait(); pending.cancel()
                with self.assertRaises(asyncio.CancelledError): await pending
                self.assertTrue(cleaned.is_set())
                self.assertEqual(context.services.used['model'], 2)
                self.assertEqual(context.services.budget.held['model'], 0)
                settlements = [f for e, f in context.services.events if e == 'external-budget-settled']
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
