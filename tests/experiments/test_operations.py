"""Real Application searches and verified adoption with fake model responses."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from fruitfly_agent.experiments.configuration import load_configuration
from fruitfly_agent.experiments.composition import prepare_experiment, application_factory
from fruitfly_agent.experiments.operations.improve import run as improve
from fruitfly_agent.experiments.operations.evolve import run as evolve
from fruitfly_agent.experiments.records import RunRecords
from fruitfly_agent.interactive import AgentApplication
from fruitfly_agent.lab.improvement.registration import EDITOR_CONFIG, ASSESSOR_CONFIG
from tests.support.experiments import workspace, factory_builder
from tests.support.faux_provider import FauxProvider
from tests.support.task_packs import install, package


class OperationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        workspace(self.root)
        self.records = RunRecords(self.root)
        self.provider = FauxProvider()
        self.registry = Mock()
        self.registry.create.return_value = self.provider

    async def test_file_search_runs_two_trials_and_keeps_original_defaults(self):
        prepared = prepare_experiment(load_configuration(self.root), 'improvement')
        record = self.records.create('improvement', prepared.summary())
        original = prepared.config_path.read_bytes()
        for text in ('baseline output', 'revised output'):
            self.provider.respond_text(text)
        with patch('fruitfly_agent.experiments.operations.improve.application_factory', side_effect=factory_builder(self.registry)):
            result = await improve(prepared, record, self.records, lambda event: None)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['usage'], {'model': 2, 'execution': 2})
        self.assertEqual(len(self.provider.calls), 2)
        self.assertEqual(prepared.config_path.read_bytes(), original)
        plan_path = next((self.root / '.fruitfly/improvement/jobs').glob('*/plan.json'))
        plan = json.loads(plan_path.read_text())
        self.assertEqual(plan['plan']['strategy_id'], 'simple')
        self.assertEqual(record['links']['Assurance'], 'selected')
        self.assertTrue((self.root / record['links']['Workflow journal']).is_file())

    async def test_assessment_and_editor_receive_their_own_models(self):
        workspace(self.root, models={'editor': 'editor', 'assessor': 'assessor'})
        prepared = prepare_experiment(load_configuration(self.root), 'improvement')
        record = self.records.create('improvement', prepared.summary())
        runtime = prepared.stage_runtime(self.records.directory(record['id']))
        factory = application_factory(prepared, runtime, provider_registry=self.registry)
        application = AgentApplication(factory)
        await application.start()
        try:
            components = application.runtime_manifest['models']
            self.assertEqual({entry['profile'] for entry in components.values()}, {'executor', 'editor', 'assessor'})
            # Public assembly config components are carried by the runtime handle contract.
            handle = await factory.open(resume=False, session_path=None)
            try:
                self.assertEqual(handle.components[EDITOR_CONFIG].model, 'offline-editor')
                self.assertEqual(handle.components[ASSESSOR_CONFIG].model, 'offline-assessor')
            finally:
                await handle.close()
        finally:
            await application.close()
        self.assertEqual(self.provider.calls, [])

    async def test_rsi_verifies_and_adopts_only_in_its_experiment_copy_then_resumes_without_replay(self):
        value = package()
        for partition in ('train', 'validation', 'holdout'):
            value[partition] = [{'id': partition + '-1', 'input': 'Independent ' + partition, 'expected': 'A'}]
        install(self.root, value)
        workspace(self.root, task={'source': 'files', 'pack': value['id']}, rsi={'max_generations': 1})
        prepared = prepare_experiment(load_configuration(self.root), 'rsi')
        record = self.records.create('rsi', prepared.summary())
        original = prepared.config_path.read_bytes()
        for text in ('wrong', 'A') * 4:
            self.provider.respond_text(text)
        with patch('fruitfly_agent.experiments.operations.evolve.application_factory', side_effect=factory_builder(self.registry)):
            result = await evolve(prepared, record, self.records, lambda event: None)
            calls = len(self.provider.calls)
            resumed = await evolve(prepared, record, self.records, lambda event: None, resume=True)
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(resumed['status'], 'complete')
        self.assertEqual(calls, 8)
        self.assertEqual(len(self.provider.calls), calls)
        self.assertEqual(prepared.config_path.read_bytes(), original)
        saved = json.loads((self.root / '.fruitfly/evolution' / (record['id'] + '.json')).read_text())
        self.assertEqual(saved['steps'], 1)
        self.assertEqual(saved['budget_state']['used']['model'], 8)
        candidates = list((self.root / '.fruitfly/improvement/candidates').glob('*.json'))
        self.assertEqual(len(candidates), 1)
        self.assertEqual(json.loads(candidates[0].read_text())['status'], 'adopted')

    async def test_cancelled_trial_closes_and_keeps_its_record_link(self):
        import asyncio
        from tests.support.improvers import OfflineRunner
        from fruitfly_agent.lab.improvement.api import WorkflowBindings
        entered, closed = asyncio.Event(), asyncio.Event()
        class Hanging(OfflineRunner):
            async def execute(self, *args):
                entered.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    closed.set()
        original_builder = factory_builder(self.registry)
        def builder(prepared, path):
            factory = original_builder(prepared, path)
            # Supply the runner through the public construction interface.
            return type(factory)(cwd=self.root, environment=prepared.environment, config_path=str(path),
                provider_registry=self.registry,
                improvement_bindings=replace(factory.improvement_bindings, runner=lambda *args: Hanging()))
        prepared = prepare_experiment(load_configuration(self.root), 'improvement')
        record = self.records.create('improvement', prepared.summary())
        with patch('fruitfly_agent.experiments.operations.improve.application_factory', side_effect=builder):
            work = asyncio.create_task(improve(prepared, record, self.records, lambda event: None))
            await entered.wait()
            work.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await work
        self.assertTrue(closed.is_set())
        self.assertIn('improvement', record['links'])

    async def test_simple_i_search_uses_downstream_episodes_and_generic_editor_instructions(self):
        from tests.support.self_improver import experiment_factory
        original_factory, provider, request = experiment_factory(self.root)
        workspace(self.root, task={'source': 'editor', 'material': 'editor'})
        prepared = prepare_experiment(load_configuration(self.root), 'improvement')
        self.assertEqual(prepared.request.component_ids, ('improvement-editor',))
        self.assertEqual(dict(prepared.request.execution_parameters)['inner_strategy'], 'simple')
        self.registry.create.return_value = provider
        record = self.records.create('improvement', prepared.summary())
        with patch('fruitfly_agent.experiments.operations.improve.application_factory', side_effect=factory_builder(self.registry)):
            result = await improve(prepared, record, self.records, lambda event: None)
        self.assertEqual(result['status'], 'completed')
        self.assertGreater(len(provider.calls), 0)
        self.assertLessEqual(result['usage']['model'], 512)
        self.assertEqual(record['links']['Assurance'], 'selected')
        self.assertTrue(any('STEP' in call['system_prompt'] for call in provider.calls))
