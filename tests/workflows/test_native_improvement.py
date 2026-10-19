"""The three native methods reach confirmation, exact activation and recovery offline."""
import asyncio
import io
import json
from pathlib import Path
import tempfile
import unittest

from fruitfly_agent.interactive import AgentApplication, TerminalFrontend
from fruitfly_agent.lab.algorithms.targets import state_artifact_path
from tests.support.improvers import offline_factory, QueueEditor
from tests.support.task_packs import package, install


TARGETS = ('execution-workflow', 'skill-document', 'learned-memory')


def make_factory(root, *, source=False):
    payload = package()
    payload['compatible_targets'] = list(TARGETS)
    install(root, payload)
    factory = offline_factory(root, 'opro')
    factory.configuration.set_mechanism('opro', enabled=False)
    for identity in TARGETS:
        factory.configuration.set_mechanism(identity, enabled=True)
    if source:
        directory = root / '.skills' / 'review'
        directory.mkdir(parents=True)
        (directory / 'SKILL.md').write_text('---\nname: code-review\ndescription: Review code\n---\n# Skill\nRead references/check.md first.')
        (directory / 'references').mkdir()
        (directory / 'references' / 'check.md').write_text('Verify concrete failures.')
        factory.configuration.set_parameter('skill-document', 'source_path', '.skills/review/SKILL.md')
    factory.configuration.save()
    factory.reload_configuration()
    return factory


def script(provider, values):
    for value in values:
        provider.respond_text(value)


class NativeImprovementTests(unittest.IsolatedAsyncioTestCase):
    async def open_app(self, root, **kwargs):
        factory = make_factory(root, **kwargs)
        app = AgentApplication(factory)
        await app.start()
        return app, factory, factory._current_runtime_config.provider

    async def test_skill_source_to_confirmed_state_activation_and_session_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app, factory, provider = await self.open_app(root, source=True)
            source = root / '.skills/review/SKILL.md'
            original = source.read_bytes()
            before = factory.system_version()
            try:
                self.assertEqual(next(t.label for t in app.improvement_targets() if t.target_id == 'skill-document'), 'Skill: code-review')
                preview = app.improvement_preview(target_id='skill-document', method_id='skill-edit',
                    pack_id='project', parameters={'rounds': 1})
                self.assertEqual(provider.calls, [])
                edits = json.dumps([dict(op='add', old='', new='Check the actual task requirements before answering.')])
                script(provider, ['wrong', 'wrong', edits, 'B', 'A', 'wrong', 'SECRET_ANSWER'])
                records = await app.improve('', preview_token=preview.preview_token)
                self.assertEqual(len(records), 1)
                record = records[0]
                self.assertEqual(record.role, 'S')
                self.assertIn('Passed', dict(record.evidence)['Independent confirmation'])
                self.assertEqual(factory.system_version(), before)
                self.assertEqual(source.read_bytes(), original)
                self.assertNotIn('PRIVATE', str(provider.calls[2]['messages']))
                self.assertNotIn('SECRET_ANSWER', str(provider.calls[2]['messages']))
                candidate = factory._versions.versions.read_candidate(dict(record.evidence)['Version candidate'])
                self.assertEqual((candidate.version.harness, candidate.version.improver), (before.harness, before.improver))
                self.assertNotEqual(candidate.version.state, before.state)
                await app.adopt_candidate(record.candidate_id)
                self.assertEqual(factory.system_version(), candidate.version)
                active_provider = factory._current_runtime_config.provider
                active_provider.respond_text('done')
                await app.submit('Review this code')
                prompt = active_provider.calls[-1]['system_prompt']
                self.assertIn('Check the actual task requirements', prompt)
                self.assertIn(str(source.parent.resolve()), prompt)
                self.assertEqual(source.read_bytes(), original)
                path = Path(app.status.session_path)
            finally:
                await app.close()
            restored = AgentApplication(factory)
            await restored.start(resume=True, session_path=path)
            try:
                self.assertEqual(factory.system_version(), candidate.version)
                target = factory._current_targets['skill-document']
                self.assertIn('Check the actual task requirements', target.snapshot().text)
                self.assertEqual(factory.candidate_store.read(record.candidate_id).status, 'adopted')
            finally:
                await restored.close()

    async def test_memory_curriculum_confirmation_and_state_only_activation(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, factory, provider = await self.open_app(Path(tmp))
            try:
                before = factory.system_version()
                preview = app.improvement_preview(target_id='learned-memory', method_id='memory-exploration',
                    pack_id='project', parameters={'rounds': 1})
                script(provider, ['wrong', '[0]', 'wrong', '# Memory\nVerify the visible result before reporting success.',
                    'B', 'A', 'wrong', 'SECRET_ANSWER'])
                records = await app.improve('', preview_token=preview.preview_token)
                self.assertEqual(len(records), 1)
                await app.adopt_candidate(records[0].candidate_id)
                after = factory.system_version()
                self.assertEqual((before.harness, before.improver), (after.harness, after.improver))
                self.assertNotEqual(before.state, after.state)
                state = factory._versions.snapshots.read(after.state)
                self.assertIn('Verify the visible result', next(f.content for f in state.files
                    if f.path == state_artifact_path('learned-memory')))
                self.assertFalse(any('SECRET_ANSWER' in str(c['messages']) for c in provider.calls[:4]))
            finally:
                await app.close()

    async def test_workflow_confirmation_harness_only_activation_and_actual_steps(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, factory, provider = await self.open_app(Path(tmp))
            try:
                before = factory.system_version()
                preview = app.improvement_preview(target_id='execution-workflow', method_id='workflow-search',
                    pack_id='project', parameters={'rounds': 1, 'reflection_steps': 0})
                workflow = json.dumps({'steps': ['Solve the task.', 'Review and return the final answer only.']})
                script(provider, ['wrong', 'wrong', workflow, 'draft', 'A', 'draft', 'B', 'wrong', 'draft', 'SECRET_ANSWER'])
                records = await app.improve('', preview_token=preview.preview_token)
                self.assertEqual(len(records), 1)
                self.assertEqual(factory.candidate_store.read(records[0].candidate_id).metric_calls, 6)
                self.assertEqual(len(provider.calls), 10)
                await app.adopt_candidate(records[0].candidate_id)
                after = factory.system_version()
                self.assertNotEqual(before.harness, after.harness)
                self.assertEqual((before.state, before.improver), (after.state, after.improver))
                active = factory._current_runtime_config.provider
                script(active, ['draft', 'final'])
                await app.submit('A new task')
                self.assertEqual(len(active.calls), 2)
                self.assertIn('Solve the task.', active.calls[0]['system_prompt'])
                self.assertEqual(active.calls[1]['messages'][-1].content, 'Review and return the final answer only.')
            finally:
                await app.close()

    async def test_failed_confirmation_and_exhausted_confirmation_publish_no_candidate(self):
        for mode in ('regression', 'budget'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                app, factory, provider = await self.open_app(Path(tmp))
                try:
                    before = factory.system_version()
                    preview = app.improvement_preview(target_id='skill-document', method_id='skill-edit', pack_id='project',
                        parameters={'rounds': 1, 'max_model_calls': 6 if mode == 'budget' else 10})
                    edit = json.dumps([dict(op='add', old='', new='Reusable procedure')])
                    script(provider, ['wrong', 'wrong', edit, 'B', 'A', 'SECRET_ANSWER', 'wrong'])
                    records = await app.improve('', preview_token=preview.preview_token)
                    self.assertEqual(records, ())
                    self.assertEqual(app.candidates(), ())
                    self.assertEqual(factory.system_version(), before)
                    self.assertEqual(len(provider.calls), 6 if mode == 'budget' else 7)
                finally:
                    await app.close()

    async def test_missing_holdout_wrong_binding_and_changed_source_reject_offline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app, factory, provider = await self.open_app(root, source=True)
            try:
                with self.assertRaisesRegex(ValueError, 'holdout'):
                    app.improvement_preview(target_id='skill-document', method_id='skill-edit', pack_id='configured-cases')
                with self.assertRaisesRegex(ValueError, 'does not support'):
                    app.improvement_preview(target_id='learned-memory', method_id='skill-edit', pack_id='project')
                preview = app.improvement_preview(target_id='skill-document', method_id='skill-edit', pack_id='project')
                (root / '.skills/review/references/check.md').write_text('changed dependency')
                with self.assertRaisesRegex(ValueError, 'parent H/S/I changed'):
                    await app.improve('', preview_token=preview.preview_token)
                self.assertEqual(provider.calls, [])
            finally:
                await app.close()

    async def test_terminal_target_shows_only_compatible_algorithm_description_and_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, factory, provider = await self.open_app(Path(tmp))
            try:
                editor = QueueEditor()
                editor.send('/improvement', '@Target ·', '@Skill document', '@Skill document optimization', '@Details · Skill document optimization',
                    'q', '/exit')
                output = io.StringIO()
                editor.output = output
                await TerminalFrontend(app, input_stream=io.StringIO(), output_stream=output, line_editor=editor).run()
                rendered = output.getvalue()
                self.assertNotIn('Edits per update', rendered)
                self.assertNotIn('JSON overrides', rendered)
                self.assertIn('bounded edits', rendered)
                self.assertIn('Implementation:', rendered)
                self.assertIn('Parameters:', rendered)
                self.assertNotIn('Configuration location', rendered)
                self.assertNotIn('Workflow search', rendered)
                self.assertNotIn('Exploratory memory learning', rendered)
                self.assertNotIn('DreamRSI', rendered)
                self.assertEqual({m.method_id for m in app.improvement_methods('S', 'skill-document')}, {'skill-edit'})
                self.assertEqual(provider.calls, [])
            finally:
                await app.close()

    async def test_prepared_runtime_cannot_smuggle_unregistered_state_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, factory, provider = await self.open_app(Path(tmp))
            try:
                manifest = dict(app.runtime_manifest)
                reference = factory.artifact_store.put_text('unknown retained state').artifact_id
                manifest['data_artifacts'] = [*manifest.get('data_artifacts', ()),
                    {'key': 'unregistered-state', 'id': reference, 'role': 'S'}]
                with self.assertRaisesRegex(ValueError, 'registered snapshot source'):
                    factory._versions.freeze(manifest=manifest)
                self.assertEqual(provider.calls, [])
            finally:
                await app.close()
