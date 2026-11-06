"""Actual candidate directories and read results use one ordinary assembler."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.data_model import UserMessage
from fruitfly_agent.core.loop import run_agent_loop
from fruitfly_agent.core.session import Session
from fruitfly_agent.lab.catalog import AssemblyContext, MechanismSelection, assemble_lab, builtin_catalog
from fruitfly_agent.improvement.contracts.versions import canonical_json
from fruitfly_agent.run.storage.artifacts import DataArtifactStore
from fruitfly_agent.run.storage.retained_state import RetainedStateStore
from fruitfly_agent.run.runtime.maintenance import RetainedRuntimeService
from tests.support.faux_provider import FauxProvider
from tests.support.retained import memory


class MemorySkillWorkflowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.provider = FauxProvider()

    def assemble(self, *, skills=None, memories=None, extra=()):
        selections = [MechanismSelection(name) for name in ('local-env', 'read-tool', 'skills', 'file-memory')]
        changes = {'memory-library': {'documents': canonical_json(memories or [])}}
        if skills is not None:
            changes['skill-library'] = {'documents': canonical_json(skills)}
        resources = []
        result = assemble_lab(AgentLoopConfig(provider=self.provider, model='fake'), catalog=builtin_catalog(),
            selections=tuple(selections) + extra,
            context=AssemblyContext(self.root, None, 'fake', lambda *_: self.fail('unexpected auxiliary model'), resource_sink=resources, component_settings={key: {'content': values} for key, values in changes.items()}))
        self.addCleanup(result.config.readable_resources.close)
        return result

    async def test_skill_description_and_body_candidates_change_actual_execution(self):
        baseline = self.assemble()
        target = baseline.components['text-target:skill-library']
        candidate = deepcopy(target.entries)
        candidate[0]['description'] = 'Use this skill when the candidate marker is relevant.'
        candidate[0]['body'] = 'CANDIDATE PROCEDURE ONLY'
        payload = json.loads(target.snapshot().text)
        payload['content']['documents'] = canonical_json(candidate)
        target.validate(canonical_json(payload))
        runtime = self.assemble(skills=target.parse(canonical_json(payload)) and candidate)
        resource = runtime.config.readable_resources
        uri = f'resource://{resource.scope}/skills/.fruitfly/skill-library/{candidate[0]["id"]}/SKILL.md'
        self.provider.respond_tool_call('read', {'path': uri}); self.provider.respond_text('done')
        result = await run_agent_loop(runtime.config, [UserMessage('Use candidate marker')], context_pipeline=runtime.context_pipeline)
        self.assertFalse(result.is_error)
        self.assertIn(candidate[0]['description'], self.provider.calls[0]['system_prompt'])
        self.assertNotIn(candidate[0]['body'], self.provider.calls[0]['system_prompt'])
        self.assertTrue(any(candidate[0]['body'] in m.text for m in result.messages if m.role == 'toolResult'))
        self.assertNotEqual(candidate[0]['body'], target.entries[0]['body'])

    async def test_memory_body_is_read_only_after_the_model_requests_it(self):
        note = memory(body='PRIVATE RETAINED BODY')
        runtime = self.assemble(memories=[note])
        resource = runtime.config.readable_resources
        uri = f'resource://{resource.scope}/retained-memory/{note["id"]}.md'
        self.provider.respond_tool_call('read', {'path': uri}); self.provider.respond_text('done')
        result = await run_agent_loop(runtime.config, [UserMessage('editor preference')], context_pipeline=runtime.context_pipeline)
        self.assertFalse(result.is_error)
        self.assertIn(note['description'], self.provider.calls[0]['system_prompt'])
        self.assertNotIn(note['body'], self.provider.calls[0]['system_prompt'])
        self.assertTrue(any(note['body'] in m.text for m in result.messages if m.role == 'toolResult'))

    def test_candidate_cannot_rewrite_skill_origin_or_memory_provenance(self):
        runtime = self.assemble(memories=[memory()])
        for key, field, value in (('skill-library', 'origin', {}), ('memory-library', 'scope', 'global')):
            target = runtime.components['text-target:' + key]
            changed = deepcopy(target.entries); changed[0][field] = value
            payload = json.loads(target.snapshot().text); payload['content']['documents'] = canonical_json(changed)
            with self.subTest(key=key), self.assertRaises(ValueError):
                target.validate(canonical_json(payload))

    async def test_committed_memory_is_available_to_a_new_session_without_rewriting_sources(self):
        artifacts = DataArtifactStore(self.root / '.fruitfly/artifacts')
        store = RetainedStateStore(self.root / '.fruitfly/retained/project', artifacts)
        runtime = self.assemble()
        with Session(self.root / 'first.jsonl') as session:
            service = RetainedRuntimeService(session=session, session_id='first', components=runtime.components, store=store)
            update = store.begin('extract', 'first-update')
            store.finish(update, status='completed', key='memory-library', text=canonical_json([memory()]))
            self.assertEqual([], service.describe('memory')['entries'])
            service.review(update, 'commit')
        restored = RetainedStateStore(store.root, artifacts)
        second = self.assemble(memories=json.loads(restored.library('memory-library')))
        self.assertEqual(memory()['body'], second.components['text-target:memory-library'].list_entries()[0]['body'])
        self.assertFalse((self.root / '.skills').exists())

    def test_removed_single_document_mechanism_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'unknown mechanism'):
            self.assemble(extra=(MechanismSelection('skill-document'),))

    def test_bounded_memory_catalog_keeps_the_complete_directory_readable(self):
        entries = [memory('memory-' + str(i), body='A body omitted from the directory.') for i in range(30)]
        runtime = self.assemble(memories=entries)
        stage = next(s for s in runtime.context_pipeline.stages if s.stage_id == 'file-memory')
        text = stage.mechanism.text
        self.assertLessEqual(len(text), 5000)
        self.assertIn('INDEX.md', text)
        self.assertNotIn(entries[0]['body'], text)
        resources = runtime.config.readable_resources
        uri = f'resource://{resources.scope}/retained-memory/INDEX.md'
        # Read through the same tool resource path as the model.
        self.assertIsNotNone(resources)
        self.assertIn('memory-29', resources.read(uri).decode())

    def test_oversized_library_is_rejected_before_a_trial_can_be_offered(self):
        from fruitfly_agent.lab.context_manager.augmentation.skills.library import builtin_entries
        entries = builtin_entries()
        for entry in entries:
            entry['body'] = 'x' * 30000
        with self.assertRaisesRegex(ValueError, 'component text budget'):
            self.assemble(skills=entries)
