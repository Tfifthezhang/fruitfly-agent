"""Frozen plans and persistent adoption through the public workflow facade."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from fruitfly_agent.interactive import AgentApplication
from tests.support.improvers import offline_factory, improve


class ImprovementFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_state_changes_invalidate_preview_and_persistent_adoption(self):
        for phase in ('preview', 'adoption'):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as tmp:
                factory = offline_factory(Path(tmp))
                app = AgentApplication(factory)
                await app.start()
                try:
                    preview = app.workflow_preview(factory.test_request)
                    if phase == 'adoption':
                        record, = await app.improve('', preview_token=preview.preview_token)
                    memory = factory.cwd / '.fruitfly/memory/MEMORY.md'
                    memory.parent.mkdir(parents=True, exist_ok=True)
                    memory.write_text('Different learning state')
                    with self.assertRaisesRegex(ValueError, 'conditions changed|H/I/S'):
                        if phase == 'preview':
                            await app.improve('', preview_token=preview.preview_token)
                        else:
                            await app.adopt_candidate(record.candidate_id)
                finally:
                    await app.close()

    async def test_multiple_components_publish_and_bind_together(self):
        with tempfile.TemporaryDirectory() as tmp:
            factory = offline_factory(Path(tmp))
            factory.test_request = replace(factory.test_request, component_ids=('base_prompt', 'tool-guidance.read'))
            app = AgentApplication(factory)
            await app.start()
            try:
                original = app.runtime_manifest
                record, = await improve(app, factory)
                self.assertEqual(app.runtime_manifest, original)
                self.assertIn('Version candidate', dict(record.evidence))
                await app.adopt_candidate(record.candidate_id)
                self.assertIn('Use exact answers.', factory._current_runtime_config.system_prompt)
                read = next(t for t in factory._current_runtime_config.tools if t.name == 'read')
                self.assertIn('Use exact answers.', read.description)
            finally:
                await app.close()
