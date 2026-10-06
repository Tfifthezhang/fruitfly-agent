"""Bundled prompt choices use the existing configuration, search and restore paths."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from fruitfly_agent.interactive import AgentApplication
from fruitfly_agent.lab.base_prompt import get_builtin
from fruitfly_agent.run.application import RunApplicationFactory
from tests.support.faux_provider import FauxProvider
from tests.support.materials import _write_models, _write_cases


class BasePromptFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_each_prompt_can_be_selected_optimized_adopted_and_restored(self):
        for reference in ('assistant-default',):
            with self.subTest(reference=reference), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                _write_models(root); _write_cases(root)
                provider = FauxProvider()
                registry = Mock(); registry.create.return_value = provider
                factory = RunApplicationFactory(cwd=root, environment={}, provider_registry=registry)
                snapshot = factory.configuration.snapshot()
                self.assertEqual((reference,), snapshot.prompt_options)
                self.assertEqual(get_builtin(reference).label, dict(snapshot.prompt_option_labels)[reference])
                self.assertEqual(get_builtin(reference).text, factory.configuration.preview_prompt(reference)[2])
                factory.configuration.select_prompt(reference)
                factory.configuration.set_mechanism('opro', enabled=True)
                factory.configuration.save(); factory.reload_configuration()
                app = AgentApplication(factory)
                await app.start()
                try:
                    self.assertEqual(get_builtin(reference).content_hash, app.runtime_manifest['base_prompt']['content_hash'])
                    for text in ('wrong','wrong','["Improved coding instructions"]','A','B','["Improved coding instructions"]'):
                        provider.respond_text(text)
                    candidate = (await app.optimize('improve'))[0]
                    self.assertEqual(get_builtin(reference).content_hash, factory.candidate_store.read(candidate.candidate_id).parent_target_hash)
                    self.assertEqual(get_builtin(reference).text, provider.calls[0]['system_prompt'])
                    await app.adopt_candidate(candidate.candidate_id)
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
