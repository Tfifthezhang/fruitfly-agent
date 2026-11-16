"""Working files survive failures, isolate writers and consume real configuration."""
import json
from pathlib import Path
from dataclasses import replace
import tempfile
import unittest
from fruitfly_agent.run.storage.artifacts import DataArtifactStore
from fruitfly_agent.run.storage.work_products import WorkProductStore
from fruitfly_agent.lab.catalog import builtin_catalog
from fruitfly_agent.lab.agents.work_products.methods.managed.algorithm import work_product_tools
from fruitfly_agent.lab.agents.submissions import saved_submission_tool
from fruitfly_agent.core.tool_runtime import ToolCallContext
from fruitfly_agent.lab.catalog.adapters.parameters import ParameterTarget
from fruitfly_agent.run.configuration import HarnessProfile
from fruitfly_agent.core.session import Session
from tests.support.assembly import AssemblyWorkspace


class WorkProductTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.artifacts = DataArtifactStore(self.root / 'artifacts')
        self.store = WorkProductStore(self.root / 'work', self.artifacts)
        self.parameters = builtin_catalog().get('work-products').descriptor.normalize_parameters({})

    async def test_atomic_revision_history_is_durable_and_child_writers_are_restricted(self):
        child = self.store.writer('child-a')
        first = child.save('analysis', 'supported finding', 0)
        self.assertEqual(1, first['revision'])
        child.save('analysis', 'updated finding', 1)
        reopened = WorkProductStore(self.root / 'work', self.artifacts)
        self.assertEqual('supported finding', reopened.read('child-a', 'analysis', 1))
        self.assertEqual('updated finding', reopened.read('child-a', 'analysis', 2))
        with self.assertRaisesRegex(ValueError, 'conflict'):
            child.save('analysis', 'stale overwrite', 1)
        self.store.writer('child-b').save('private', 'other child', 0)
        self.assertEqual(['child-a'], [r['producer'] for r in child.entries()])
        with self.assertRaisesRegex(ValueError, 'outside'):
            child.read('child-b', 'private', 1)
        with self.assertRaises(ValueError):
            child.save('../escape', 'invalid', 0)
        self.artifacts._path(first['artifact_id']).write_text('tampered')
        with self.assertRaisesRegex(ValueError, 'hash'):
            reopened.read('child-a', 'analysis', 1)

    async def test_rejected_saved_submission_is_repaired_without_rewriting_the_body(self):
        body = 'retained details ' * 3000
        self.store.save('draft', json.dumps({'body': body, 'extra': None}), 0)
        accepted = []
        def submit(value):
            if set(value) != {'body'}:
                raise ValueError('extra: unexpected key')
            accepted.append(value)
        tool = saved_submission_tool(self.store, submit)
        args = {'producer': 'parent', 'name': 'draft', 'revision': 1}
        with self.assertRaisesRegex(ValueError, 'extra'):
            await tool.execute(ToolCallContext('first', tool.name, args, None))
        patch = next(t for t in work_product_tools(self.store, self.parameters) if t.name == 'patch_checkpoint')
        await patch.execute(ToolCallContext('patch', patch.name, {'name': 'draft', 'expected_revision': 1,
            'changes': [{'path': ['extra'], 'operation': 'remove'}]}, None))
        result = await tool.execute(ToolCallContext('second', tool.name, {**args, 'revision': 2}, None))
        self.assertTrue(result.terminate)
        self.assertEqual([{'body': body}], accepted)
        self.assertIn('extra', json.loads(self.store.read('parent', 'draft', 1)))

    async def test_authorized_candidate_changes_actual_tool_guidance_and_protected_fields_fail(self):
        fixture = AssemblyWorkspace(self.root)
        catalog = builtin_catalog()
        selection = next(s for s in catalog.default_selections() if s.mechanism_id == 'work-products')
        profile = HarnessProfile('test', str(fixture.model_path), 'offline', (selection,))
        with Session(self.root / 'baseline.jsonl') as session:
            baseline = fixture.assemble(profile, session, catalog=catalog)
            target = baseline.components['text-target:work-products']
            text = json.loads(target.snapshot().text)
            text['instructions']['checkpoint'] = 'Save tested progress before handing off a task.'
            candidate = json.dumps(text)
            target.validate_change(candidate, {'editable_fields': ['parameters.instructions.checkpoint']})
            values = target.parse(candidate)
            with Session(self.root / 'candidate.jsonl') as child_session:
                changed = fixture.assemble(replace(profile, mechanisms=(replace(selection, parameters=values),)), child_session, catalog=catalog)
                actual = next(t for t in changed.config.tools if t.name == 'save_checkpoint')
                self.assertEqual(text['instructions']['checkpoint'], actual.description)
                self.assertNotEqual(baseline.manifest.digest, changed.manifest.digest)
            self.assertNotEqual(target.values['checkpoint'], text['instructions']['checkpoint'])
            with self.assertRaises(ValueError):
                target.validate_options({'editable_fields': ['parameters.settings.page_characters']})
