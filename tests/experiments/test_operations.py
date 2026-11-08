"""Real Application searches and verified adoption with fake model responses."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from fruitfly_agent.experiments.configuration import load_configuration
from fruitfly_agent.experiments.composition import prepare_experiment, application_factory
from fruitfly_agent.experiments.records import RunRecords
from fruitfly_agent.interactive import AgentApplication
from fruitfly_agent.lab.improvement.registration import EDITOR_CONFIG, ASSESSOR_CONFIG
from tests.support.experiments import workspace, factory_builder
from tests.support.model_evaluation import RoleProvider
from tests.support.task_packs import install, package


class OperationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        workspace(self.root)
        self.records = RunRecords(self.root)
        self.provider = RoleProvider()
        self.registry = Mock()
        self.registry.create.return_value = self.provider


    async def test_assessment_and_editor_receive_their_own_models(self):
        workspace(self.root, models={'editor': 'editor', 'assessor': 'assessor'})
        prepared = prepare_experiment(load_configuration(self.root), 'improvement')
        record = self.records.create('improvement', prepared.summary())
        runtime = prepared.stage_runtime(self.records.directory(record['id']))
        factory = application_factory(prepared, runtime, provider_registry=self.registry)
        application = AgentApplication(factory)
        await application.start()
        try:
            components = application.runtime_manifest['model_roles']
            self.assertEqual({entry['profile'] for entry in components.values()}, {'executor', 'editor', 'assessor'})
            self.assertEqual(self.registry.create.call_count, 1, 'unused I clients stay lazy')
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
