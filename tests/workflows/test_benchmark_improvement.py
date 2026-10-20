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
from fruitfly_agent.lab.improvement.api import TaskReference, TaskRunEvidence, EvidenceArtifact
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
        self.tasks = self.tasks[:selection['task_limit']]
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
        provider.respond_text('SUCCESS' if 'Use exact answers.' in json.loads(packet['text'])['base_prompt'] else 'wrong')
        registry = Mock()
        registry.create.return_value = provider
        receipt = await execute_trial(packet, workspace=work, config_path=Path(self.runtime['config_path']),
            profile=self.runtime['profile'], source_root=self.source_root, output_directory=root / 'logs',
            provider_registry=registry, environment={})
        assert provider.calls[0]['system_prompt'].startswith(json.loads(packet['text'])['base_prompt']), repr(provider.calls[0]['system_prompt'])
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


from tests.support.improvers import offline_factory


class BenchmarkImprovementTests(unittest.IsolatedAsyncioTestCase):
    async def open_app(self, root):
        factory = offline_factory(root)
        app = AgentApplication(factory)
        await app.start()
        self.addAsyncCleanup(app.close)
        return app, factory

    async def test_task_stream_runs_full_application_trials_without_grading_feedback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            app, factory = await self.open_app(root)
            parent = factory.system_version()
            executor = ApplicationTaskExecutor(root)
            preview = factory.benchmark_task_preview({'benchmark_id': 'terminal-bench', 'variant': 'no_gpu',
                'task_limit': 2, 'generator_id': 'offline-rule', 'component_ids': ('base_prompt',)}, executor)
            self.assertEqual(executor.prepared, 0)
            self.assertEqual(await app.improve('', preview_token=preview.preview_token), ())
            self.assertEqual(len(executor.calls), 8)
            self.assertEqual(factory.system_version(), parent)
            self.assertEqual(app.candidates(), ())
            self.assertIn('SUCCESS', factory._external_jobs.completion().output)
            self.assertEqual(factory._external_jobs.completion().report.model_calls, 8)
            for plan in root.glob('.fruitfly/improvement/jobs/*/plan.json'):
                self.assertNotIn('Fake official reward', plan.read_text())
            journals = list(root.glob('.fruitfly/improvement/jobs/*/events.jsonl'))
            self.assertEqual(len(journals), 2)
            self.assertTrue(all('Fake official reward' not in p.read_text() for p in journals))

    async def test_corrupt_receipt_rejects_before_any_proposal_or_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            app, factory = await self.open_app(root)
            executor = ApplicationTaskExecutor(root, corrupt=True)
            preview = factory.benchmark_task_preview({'benchmark_id': 'terminal-bench', 'variant': 'no_gpu',
                'task_limit': 1, 'generator_id': 'offline-rule'}, executor)
            with self.assertRaisesRegex(ValueError, 'receipt differs'):
                await app.improve('', preview_token=preview.preview_token)
            self.assertEqual(len(executor.calls), 1)
            self.assertFalse(app.candidates())
            self.assertEqual(app.improvement_history()[0].status, 'failed')

    async def test_cancel_during_preparation_or_trial_is_owned_by_application(self):
        for phase in ('preparation', 'trial'):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                app, factory = await self.open_app(root)
                executor = ApplicationTaskExecutor(root, block=True)
                entered, cleaned = asyncio.Event(), asyncio.Event()
                if phase == 'preparation':
                    async def prepare(selection):
                        entered.set()
                        try:
                            await asyncio.Event().wait()
                        finally:
                            cleaned.set()
                    executor.prepare_tasks = prepare
                else:
                    entered = executor.entered
                preview = factory.benchmark_task_preview({'benchmark_id': 'terminal-bench', 'variant': 'no_gpu',
                    'task_limit': 1, 'generator_id': 'offline-rule'}, executor)
                task = app.start_improvement('', preview_token=preview.preview_token)
                await asyncio.wait_for(entered.wait(), 5)
                self.assertEqual(app.state.value, 'improving')
                app.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                self.assertFalse(app.candidates())
                if phase == 'preparation':
                    self.assertTrue(cleaned.is_set())
                await app.close()

    async def test_changed_state_or_missing_generator_rejects_without_download(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            app, factory = await self.open_app(root)
            executor = ApplicationTaskExecutor(root)
            selection = {'benchmark_id': 'terminal-bench', 'variant': 'no_gpu', 'task_limit': 1}
            with self.assertRaisesRegex(ValueError, 'generator'):
                factory.benchmark_task_preview({**selection, 'generator_id': 'unknown'}, executor)
            preview = factory.benchmark_task_preview({**selection, 'generator_id': 'offline-rule'}, executor)
            memory = root / '.fruitfly/memory/MEMORY.md'
            memory.parent.mkdir(parents=True, exist_ok=True)
            memory.write_text('Changed state')
            with self.assertRaisesRegex(ValueError, 'conditions changed'):
                await app.improve('', preview_token=preview.preview_token)
            self.assertEqual(executor.prepared, 0)
