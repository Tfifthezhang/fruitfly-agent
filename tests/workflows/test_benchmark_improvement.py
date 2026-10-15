"""Full Application trials, official-executor receipts, comparison and human adoption offline."""
import asyncio
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from fruitfly_agent.interactive import AgentApplication
from fruitfly_agent.lab.algorithms.targets import SystemVersion, canonical_json, content_hash
from fruitfly_agent.lab.optimization.text_optimizer import TaskReference, TaskRunEvidence, EvidenceArtifact
from fruitfly_agent.lab.optimization.failure_processing.projection import source_case
from fruitfly_agent.run.application import RunApplicationFactory
from fruitfly_agent.run.adapters.benchmark_trials import BenchmarkTrialClient
from fruitfly_agent.run.trial import execute_trial
from tests.support.faux_provider import FauxProvider
from tests.support.materials import _write_models


class ApplicationTaskExecutor(BenchmarkTrialClient):
    """Run normal Application locally; a fake verifier replaces Docker/Harbor only."""
    def __init__(self, workspace, *, corrupt=False, block=False):
        super().__init__(workspace=workspace, environment={})
        self.calls, self.corrupt, self.block = [], corrupt, block
        self.entered = asyncio.Event()
        self.tasks = task_references()
        self.prepared = 0

    async def prepare_tasks(self, selection):
        self.prepared += 1
        source = self.workspace / "prepared-tasks"
        source.mkdir()
        materials = {}
        for task in self.tasks:
            (source / task.task_id).mkdir()
            materials[task.reference_id] = task.task_id
        return {"benchmark_id": "terminal-bench", "tasks": [t.to_dict() for t in self.tasks],
                "materials": materials, "material_root": str(source)}

    async def run(self, task, packet, *, timeout, signal=None):
        self.calls.append((task, packet.copy()))
        self.entered.set()
        if self.block:
            await asyncio.Event().wait()
        root = self.workspace / 'trials' / str(len(self.calls))
        work = root / 'workspace'
        work.mkdir(parents=True)
        provider = FauxProvider()
        provider.respond_text('SUCCESS' if packet['text'] == 'Improved guidance' else 'wrong')
        registry = Mock()
        registry.create.return_value = provider
        receipt = await execute_trial(packet, workspace=work, config_path=Path(self.runtime['config_path']),
            profile=self.runtime['profile'], source_root=self.source_root, output_directory=root / 'logs',
            provider_registry=registry, environment={})
        assert provider.calls[0]['system_prompt'].startswith(packet['text']), repr(provider.calls[0]['system_prompt'])
        assert provider.calls[0]['messages'][0].content == task.instruction
        artifacts = tuple(EvidenceArtifact(kind, 'logs/' + name, 'sha256:' + hashlib.sha256((root/'logs'/name).read_bytes()).hexdigest())
            for kind, name in [('runtime-receipt', 'trial-receipt.json'), ('trajectory', 'session.jsonl')])
        evidence = TaskRunEvidence(str(len(self.calls)), task, 'scored', float(receipt['output'] == 'SUCCESS'),
            receipt['output'], 'Fake official reward', artifacts,
            version=SystemVersion.from_dict(receipt['version']),
            conditions_id=receipt['conditions_id'], model_calls=receipt['model_calls'] + int(self.corrupt),
            runtime_digest=receipt['runtime']['digest'], environment_digest=content_hash(canonical_json(receipt['execution_environment'])))
        return {'evidence': evidence.to_dict(), 'evidence_root': str(root)}


def task_references(count=3):
    return tuple(TaskReference('terminal-bench@2.0', f'task-{i}', 'pinned', content_hash(str(i)),
        f'Complete original task {i}.', 'official-verifier', 'cpu') for i in range(count))


class BenchmarkImprovementTests(unittest.IsolatedAsyncioTestCase):
    async def setup_app(self, root, *, budget=80):
        _write_models(root)
        provider = FauxProvider()
        registry = Mock()
        registry.create.return_value = provider
        factory = RunApplicationFactory(cwd=root, environment={}, provider_registry=registry)
        for name in ('opro', 'failure-distillation', 'automatic-text-search'):
            factory.configuration.set_mechanism(name, enabled=True)
        for key, value in [('rounds', '1'), ('batch_size', '1'), ('max_model_calls', str(budget)), ('output_max_tokens', '4096')]:
            factory.configuration.set_parameter('opro', key, value)
        factory.configuration.set_parameter('automatic-text-search', 'external_trial_model_calls', '2')
        factory.configuration.save()
        factory.reload_configuration()
        app = AgentApplication(factory)
        await app.start()
        self.addAsyncCleanup(app.close)
        return app, factory, provider

    def script(self, provider, task):
        provider.respond_text(json.dumps({'tasks': [{'source_case_id': source_case(task).case_id,
            'input': 'Practice the training behavior; reply A', 'acceptance': {'expected': 'A'}}]}))
        provider.respond_text('{"accepted": true, "reason": "Matches training behavior"}')
        provider.respond_text('wrong')
        provider.respond_text('["Improved guidance"]')
        provider.respond_text('A')

    async def test_original_trials_load_candidate_and_confirmation_waits_for_adoption(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            app, factory, provider = await self.setup_app(root)
            memory = root / '.fruitfly/memory/MEMORY.md'
            memory.parent.mkdir(parents=True, exist_ok=True)
            memory.write_text('Frozen production memory')
            tasks = task_references()
            executor = ApplicationTaskExecutor(root)
            parent = factory.system_version()
            manifest = app.runtime_manifest
            preview = factory.benchmark_task_preview({'benchmark_id': 'terminal-bench', 'variant': 'no_gpu', 'task_limit': 3}, executor)
            self.script(provider, tasks[0])
            records = await app.optimize(factory._experiments.direction, preview_token=preview.preview_token)
            self.assertEqual(len(records), 1)
            self.assertEqual(len(executor.calls), 6)
            self.assertEqual(factory.system_version(), parent)
            self.assertEqual(app.runtime_manifest, manifest)
            self.assertEqual(factory.candidate_store.read(records[0].candidate_id).status, 'proposed')
            for index in range(1, 7):
                trial_memory = root/'trials'/str(index)/'workspace/.fruitfly/memory/MEMORY.md'
                self.assertEqual(trial_memory.read_text(), 'Frozen production memory')
            (root/'trials/1/workspace/.fruitfly/memory/MEMORY.md').write_text('Trial mutation')
            self.assertEqual(memory.read_text(), 'Frozen production memory')
            self.assertEqual((root/'trials/2/workspace/.fruitfly/memory/MEMORY.md').read_text(), 'Frozen production memory')
            for call in provider.calls:
                self.assertNotIn(tasks[-1].instruction, repr(call))
            detail = factory.candidate_store.read(records[0].candidate_id)
            declared = factory._versions.versions.read_candidate(dict(detail.evidence)['Version candidate'])
            await app.adopt_candidate(records[0].candidate_id)
            self.assertEqual(factory.system_version(), declared.version)
            self.assertEqual(factory.system_version().state, parent.state)
            self.assertEqual(factory.system_version().improver, parent.improver)

    async def test_memory_change_after_confirmation_rejects_adoption(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            app, factory, provider = await self.setup_app(root)
            tasks = task_references()
            executor = ApplicationTaskExecutor(root)
            preview = factory.benchmark_task_preview({'benchmark_id': 'terminal-bench', 'variant': 'no_gpu', 'task_limit': 3}, executor)
            self.script(provider, tasks[0])
            records = await app.optimize(factory._experiments.direction, preview_token=preview.preview_token)
            self.assertEqual(len(records), 1)
            manifest = app.runtime_manifest
            memory = root/'.fruitfly/memory/MEMORY.md'
            memory.parent.mkdir(parents=True, exist_ok=True)
            memory.write_text('New production experience')
            with self.assertRaisesRegex(ValueError, 'H/I/S'):
                await app.adopt_candidate(records[0].candidate_id)
            self.assertEqual(app.runtime_manifest, manifest)
            self.assertEqual(factory.candidate_store.read(records[0].candidate_id).status, 'stale')

    async def test_changed_model_catalog_cannot_activate_verified_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            app, factory, provider = await self.setup_app(root)
            tasks = task_references()
            executor = ApplicationTaskExecutor(root)
            preview = factory.benchmark_task_preview({'benchmark_id': 'terminal-bench', 'variant': 'no_gpu', 'task_limit': 3}, executor)
            self.script(provider, tasks[0])
            records = await app.optimize(factory._experiments.direction, preview_token=preview.preview_token)
            self.assertEqual(len(records), 1)
            manifest = app.runtime_manifest
            config = factory.selection.config_path.read_bytes()
            path = root/'models.yaml'
            path.write_text(path.read_text().replace('offline-model', 'different-model'))
            with self.assertRaisesRegex(ValueError, 'model or permission conditions'):
                await app.adopt_candidate(records[0].candidate_id)
            self.assertEqual(app.runtime_manifest, manifest)
            self.assertEqual(factory.selection.config_path.read_bytes(), config)
            self.assertEqual(factory.candidate_store.read(records[0].candidate_id).status, 'proposed')

    async def test_direct_task_set_runs_one_job_without_an_initial_evaluation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            app, factory, provider = await self.setup_app(root)
            tasks = task_references()
            class Executor(ApplicationTaskExecutor):
                async def prepare_tasks(self, selection):
                    self.assert_lifecycle()
                    return await super().prepare_tasks(selection)
            executor = Executor(root)
            executor.assert_lifecycle = lambda: self.assertEqual(app.state.value, 'optimizing')
            preview = factory.benchmark_task_preview({'benchmark_id':'terminal-bench','variant':'no_gpu','task_limit':3}, executor)
            self.assertEqual(executor.prepared, 0)
            self.assertEqual(provider.calls, [])
            self.script(provider, tasks[0])
            records = await app.optimize(factory._experiments.direction, preview_token=preview.preview_token)
            self.assertEqual(executor.prepared, 1)
            self.assertEqual(len(records), 1)
            self.assertEqual(len(executor.calls), 6)
            self.assertFalse((root/'.fruitfly/eval').exists())
            self.assertEqual(dict(records[0].evidence)['Original task source'], 'prepared-tasks')
            experiment_path = root / dict(records[0].evidence)['Experiment']
            self.assertEqual(json.loads(experiment_path.read_text())['task_source'], 'prepared-tasks')
            self.assertEqual(factory.candidate_store.read(records[0].candidate_id).status, 'proposed')

    async def test_cancellation_during_task_preparation_uses_application_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            app, factory, provider = await self.setup_app(root)
            executor = ApplicationTaskExecutor(root)
            entered, cleaned = asyncio.Event(), asyncio.Event()
            async def prepare(selection):
                entered.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cleaned.set()
            executor.prepare_tasks = prepare
            preview = factory.benchmark_task_preview({'benchmark_id':'terminal-bench','variant':'no_gpu','task_limit':3}, executor)
            running = app.start_optimization(factory._experiments.direction, preview_token=preview.preview_token)
            await asyncio.wait_for(entered.wait(), 5)
            with self.assertRaises(RuntimeError):
                app.enqueue('another task')
            app.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await running
            self.assertTrue(cleaned.is_set())
            self.assertEqual(provider.calls, [])
            self.assertEqual(executor.calls, [])
            self.assertEqual(app.candidates(), ())

    async def test_changed_memory_after_preview_stops_before_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            app, factory, provider = await self.setup_app(root)
            executor = ApplicationTaskExecutor(root)
            preview = factory.benchmark_task_preview({'benchmark_id': 'terminal-bench', 'variant': 'no_gpu', 'task_limit': 3}, executor)
            memory = root/'.fruitfly/memory/MEMORY.md'
            memory.parent.mkdir(parents=True, exist_ok=True)
            memory.write_text('Changed')
            with self.assertRaisesRegex(ValueError, 'H/I/S'):
                await app.optimize(factory._experiments.direction, preview_token=preview.preview_token)
            self.assertEqual(executor.prepared, 0)
            self.assertEqual(executor.calls, [])
            self.assertEqual(provider.calls, [])

    async def test_insufficient_allocation_never_starts_original_trial(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            app, factory, provider = await self.setup_app(root, budget=1)
            executor = ApplicationTaskExecutor(root)
            preview = factory.benchmark_task_preview({'benchmark_id': 'terminal-bench', 'variant': 'no_gpu', 'task_limit': 3}, executor)
            self.assertEqual(await app.optimize(factory._experiments.direction, preview_token=preview.preview_token), ())
            self.assertEqual(executor.calls, [])
            self.assertEqual(provider.calls, [])

    async def test_counter_mismatch_cannot_produce_learning_material(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            app, factory, provider = await self.setup_app(root)
            executor = ApplicationTaskExecutor(root, corrupt=True)
            preview = factory.benchmark_task_preview({'benchmark_id': 'terminal-bench', 'variant': 'no_gpu', 'task_limit': 3}, executor)
            self.assertEqual(await app.optimize(factory._experiments.direction, preview_token=preview.preview_token), ())
            self.assertEqual(provider.calls, [])
            self.assertEqual(app.candidates(), ())

    async def test_cancelled_original_trial_has_no_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            app, factory, provider = await self.setup_app(root)
            executor = ApplicationTaskExecutor(root, block=True)
            preview = factory.benchmark_task_preview({'benchmark_id': 'terminal-bench', 'variant': 'no_gpu', 'task_limit': 3}, executor)
            running = app.start_optimization(factory._experiments.direction, preview_token=preview.preview_token)
            await asyncio.wait_for(executor.entered.wait(), 5)
            app.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await running
            self.assertEqual(app.candidates(), ())
            experiments = list((root/'.fruitfly/optimization/experiments').glob('*/experiment.json'))
            self.assertEqual(json.loads(experiments[0].read_text())['status'], 'interrupted')
