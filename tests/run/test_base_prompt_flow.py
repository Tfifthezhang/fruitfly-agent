"""Bundled prompt choices use the existing configuration, search and restore paths."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from fruitfly_agent.interactive import AgentApplication
from fruitfly_agent.lab.base_prompt import get_builtin
from fruitfly_agent.run.application import RunApplicationFactory
from tests.support.faux_provider import FauxProvider
from tests.support.improvers import offline_factory, improve
from tests.support.materials import _write_models, _write_cases


class BasePromptFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_each_prompt_can_be_selected_improved_adopted_and_restored(self):
        for reference in ('assistant-default',):
            with self.subTest(reference=reference), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                _write_models(root); _write_cases(root)
                provider = FauxProvider()
                registry = Mock(); registry.create.return_value = provider
                factory = offline_factory(root)
                snapshot = factory.configuration.snapshot()
                self.assertEqual((reference,), snapshot.prompt_options)
                self.assertEqual(get_builtin(reference).label, dict(snapshot.prompt_option_labels)[reference])
                self.assertEqual(get_builtin(reference).text, factory.configuration.preview_prompt(reference)[2])
                factory.configuration.select_prompt(reference)
                factory.configuration.save(); factory.reload_configuration()
                app = AgentApplication(factory)
                await app.start()
                try:
                    self.assertEqual(get_builtin(reference).content_hash, app.runtime_manifest['base_prompt']['content_hash'])
                    candidate = (await improve(app, factory))[0]
                    self.assertIn('Use exact answers.', factory.artifact_store.read_text(candidate.artifact_id))
                    await app.adopt_candidate(candidate.candidate_id)
                    provider = factory._current_runtime_config.provider
                    provider.respond_text('done'); await app.submit('continue')
                    path = Path(app.status.session_path)
                    active = app.runtime_manifest['base_prompt']['content_hash']
                finally:
                    await app.close()
                restored = AgentApplication(factory)
                await restored.start(resume=True, session_path=path)
                try:
                    self.assertEqual(active, restored.runtime_manifest['base_prompt']['content_hash'])
                finally:
                    await restored.close()
