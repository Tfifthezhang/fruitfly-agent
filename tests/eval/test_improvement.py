"""Optional benchmark adapters use real stage contracts without Docker or models."""
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
from fruitfly_agent.improvement.workflow.services import WorkflowServices
from fruitfly_agent.lab.improvement.workflow import ImprovementWorkflow as ComponentWorkflow
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
from tests.support.pipeline import version


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
        files = [(name, hashlib.sha256((source / name).read_bytes()).hexdigest()) for name in
            ('fruitfly_agent/run/runtime/usage.py', 'fruitfly_agent/run/cli.py', 'fruitfly_eval/harbor_agent.py',
             'fruitfly_agent/core/loop.py', 'fruitfly_agent/run/configuration/profile.py',
             'fruitfly_agent/run/runtime/assembly.py', 'fruitfly_agent/runtime_spec/execution.py',
             'fruitfly_agent/core/config.py', 'fruitfly_agent/lab/catalog/configuration.py',
                     'fruitfly_agent/lab/catalog/parameters.py', 'fruitfly_agent/lab/execution_policy/__init__.py',
                     'fruitfly_agent/run/configuration/templates/components/H/execution-policy.yaml', 'fruitfly_agent/runtime_spec/profiles.py', 'fruitfly_agent/runtime_spec/selections.py', 'fruitfly_eval/runtime.py')]
        receipt = {'id': 'prepared-identity', 'runtime': {'installation': {'files': files}},
            'tasks': [{'id': 'external/task', 'path': str(task)}]}
        plan = RunPlan('experiment', version(), ('base_prompt',), generator_id='rule', feedback='scored')
        services = WorkflowServices(plan)
        context = ExecutionContext(root, artifacts, components, None, None, None, plan=plan, services=services)
        return context, request, host, receipt

    def freeze(self, context, request, host, receipt, executor):
        definition = benchmark_execution(request, host,  executor=executor)
        host_model = SimpleNamespace(agent_env={'FRUITFLY_MAX_MODEL_CALLS': '2'})
        return definition, patch('fruitfly_eval.improvement.registration.HostConfig.read', return_value=host_model), patch(
            'fruitfly_eval.improvement.registration.load_preparation', return_value=receipt)

    async def test_candidate_executes_then_official_results_drive_existing_workflow(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            context, request, host, receipt = self.fixture(root)
            calls = []
            async def executor(evaluation, host_path, *, directory, output_root, emit):
                self.assertFalse(hasattr(context.services,'budget'))
                from fruitfly_agent.lab.catalog import load_system_config
                selected = load_system_config(evaluation.runtime.config_path).select()
                candidate = selected.artifact_contents[selected.prompt] != 'baseline'
                calls.append(candidate)
                path = output_root / ('evaluation-' + str(len(calls)))
                agent = path / 'artifacts/harbor/job/trial/agent'; agent.mkdir(parents=True)
                (agent / 'session.jsonl').write_text('{"type":"message"}\n')
                (agent / 'trajectory.json').write_text('{}')
                (agent / 'model-usage.json').write_text('{"schema_version":1,"used":2,"requests":[{"id":"call-0","status":"completed","usage":null},{"id":"call-1","status":"completed","usage":null}]}')
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
                            (EditReason('base_prompt', 'Evidence-driven proposal', (request.records[0].run_id,), expected_effect='The proposed behavior appears in the subsequent execution.'),))
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

    async def test_fixed_i_benchmark_episodes_measure_downstream_changes_with_shared_budget(self):
        from copy import deepcopy
        from fruitfly_agent.core.config import AgentLoopConfig
        from fruitfly_agent.lab.improvement.editor.instructions import EditorInstructionTarget, EditorInstructions
        from tests.support.self_improver import ProceduralProvider
        from fruitfly_eval.improvement import benchmark_improver
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            context, request, host, receipt = self.fixture(root)
            context.components.register(TextComponentAdapter(EditorInstructionTarget(), 'improvement-instructions'))
            plan = replace(context.plan, component_ids=('improvement-editor',))
            context.plan = plan
            context.services = WorkflowServices(plan)
            provider = ProceduralProvider()
            context.config = context.editor_config = AgentLoopConfig(provider=provider)
            independent_task = root / 'independent'; independent_task.mkdir()
            (independent_task / 'instruction.md').write_text('Independent external task.')
            independent_receipt = deepcopy(receipt)
            independent_receipt['tasks'][0]['path'] = str(independent_task)
            independent_receipt['tasks'][0]['id'] = 'independent/task'
            second_host = root / 'independent-host.yaml'; second_host.write_text('independent host identity')
            receipts = {str(host.resolve()): receipt, str(second_host.resolve()): independent_receipt}
            calls = []
            async def executor(evaluation, host_path, *, directory, output_root, emit):
                from fruitfly_agent.lab.catalog import load_system_config
                selected = load_system_config(evaluation.runtime.config_path).select()
                changed = selected.artifact_contents[selected.prompt] != 'baseline'
                calls.append((str(host_path), changed))
                path = output_root / ('nested-' + str(len(calls)))
                agent = path / 'artifacts/harbor/job/trial/agent'; agent.mkdir(parents=True)
                (agent / 'session.jsonl').write_text('{}\n')
                (agent / 'model-usage.json').write_text('{"schema_version":1,"used":1,"requests":[{"id":"call-0","status":"completed","usage":null}]}')
                return {'evaluation_id': path.name, 'status': 'completed', 'errors': {},
                    'metrics': [{'name': 'official_reward', 'value': float(changed)}]}, path
            development = benchmark_execution(request, host,  execution_id='development')
            independent = benchmark_execution(request, second_host,  execution_id='independent')
            study = benchmark_improver((development,), (independent,), executor=executor)
            supplied = (('inner_strategy','harness2'),)
            with patch('fruitfly_eval.improvement.registration.HostConfig.read', side_effect=lambda workspace, path:
                    SimpleNamespace(agent_env={'FRUITFLY_MAX_MODEL_CALLS': '2'}, receipt=receipts[str(Path(path).resolve())])), patch(
                    'fruitfly_eval.improvement.registration.load_preparation', side_effect=lambda host, *args: host.receipt):
                prepared = study.prepare(context, ExecutionRequest('', (), ('improvement-editor',),
                    'benchmark-editor-study', 'task', 'scored', supplied))
                self.assertFalse(calls)
                ports = study.build(context, prepared)
                baseline = context.components.snapshot()
                document = baseline.component('improvement-editor')
                values = json.loads(document.files[0].text); values['instructions']['invariant'] += ' STEP'
                changed = replace(document, files=(ComponentFile('instructions.txt', json.dumps(values)),))
                candidate = HarnessSnapshot(tuple(changed if d.component_id == changed.component_id else d for d in baseline.components))
                before = await ports.runner.trial(baseline, 'development')
                after = await ports.runner.trial(candidate, 'development')
                confirmation = await ports.runner.trial(candidate, 'verification')
                self.assertEqual((before.failures, after.failures, confirmation.failures), (0, 0, 0))
                self.assertEqual((before.mean_gain, after.mean_gain, confirmation.mean_gain), (0, 1, 1))
                self.assertTrue(any(Path(path).resolve() == second_host.resolve() for path, _ in calls))
                self.assertEqual(context.services.used['execution'], len(calls))
                self.assertEqual(context.services.used['model'], len(calls) + len(provider.calls))
                self.assertFalse(hasattr(context.services,'budget'))
                self.assertEqual(context.components.snapshot(), baseline)
            await context.services.close()

    async def test_timeout_collects_partial_evidence_and_observed_usage(self):
        from fruitfly_agent.improvement.workflow.operations import run_stage
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
            context.services = WorkflowServices(context.plan)
            with host_patch, receipt_patch:
                prepared = definition.prepare(context, ExecutionRequest('', (), ('base_prompt',), 'benchmark-task', 'task', 'scored'))
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
            self.assertTrue(any(r.path.endswith('session.jsonl') for r in resources))
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
            self.assertTrue(any(r.path.endswith('session.jsonl') for r in resources))
