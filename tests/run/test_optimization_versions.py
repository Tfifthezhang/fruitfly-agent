"""Offline reference retention, structured review, and startup version selection."""
import io
import asyncio
from dataclasses import replace, asdict
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, AsyncMock, patch
from fruitfly_agent.interactive import AgentApplication
from fruitfly_agent.interactive.optimization import CandidateSection
from fruitfly_agent.interactive import TerminalFrontend
from fruitfly_agent.interactive.terminal.configuration import TerminalConfigurationFrontend
from fruitfly_agent.interactive.terminal.menu import RawTerminalMenuInput, TerminalMenuRenderer
from fruitfly_agent.run.application import RunApplicationFactory
from fruitfly_agent.run.artifacts import DataArtifactStore
from fruitfly_agent.run.optimization import CandidateStore
from fruitfly_agent.run.retention import compact_candidates
from fruitfly_agent.run.startup_versions import RunStartupVersions
from fruitfly_agent.lab.base_prompt.target import BasePromptTarget
from fruitfly_agent.lab.context_manager.augmentation.skills.target import SkillGuidanceTarget
from tests.support.faux_provider import FauxProvider
from tests.support.materials import _write_models, _write_cases
from fruitfly_agent.lab.optimization.text_optimizer import TextProposal, SearchReport, TokenUsage


class RetentionTests(unittest.TestCase):
    def test_latest_per_scope_collects_only_unreferenced_owned_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / '.fruitfly/config.yaml'
            config.parent.mkdir()
            config.write_text('profiles: {}')
            store = CandidateStore(root / '.fruitfly/optimization/candidates', DataArtifactStore(root / '.fruitfly/artifacts'))
            def create(text, profile='default', target=None):
                return store.create(text=text, algorithm='custom', parent_manifest={'digest':'parent'},
                    cases_digest='cases', direction='improve', seed_score=0, validation_score=1,
                    metric_calls=1, snapshot=target or BasePromptTarget('original').snapshot(),
                    config_path=str(config), profile_id=profile)
            old = create('obsolete')
            session_owned = create('session text')
            latest = create('latest')
            other = create('other profile', 'other')
            skill = create('skill latest', target=SkillGuidanceTarget('original guidance',4000).snapshot())
            sessions = root / '.fruitfly/sessions'
            sessions.mkdir()
            (sessions / 'old.jsonl').write_text(json.dumps({'reference':session_owned.artifact_id})+'\n')
            unrelated = store.artifacts.put_text('external artifact')
            removed = compact_candidates(root, store, config)
            self.assertEqual({old.candidate_id, session_owned.candidate_id}, set(removed))
            self.assertEqual({latest.candidate_id, other.candidate_id, skill.candidate_id}, {r.candidate_id for r in store.list()})
            self.assertEqual('session text', store.artifacts.read_text(session_owned.artifact_id))
            self.assertEqual('external artifact', store.artifacts.read_text(unrelated.artifact_id))
            with self.assertRaises(ValueError):
                store.artifacts.read_text(old.artifact_id)

    def test_rsi_reference_and_malformed_session_prevent_destructive_collection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); config = root / 'config.yaml'; config.write_text('{}')
            store = CandidateStore(root / '.fruitfly/optimization/candidates', DataArtifactStore(root / '.fruitfly/artifacts'))
            def create(text):
                return store.create(text=text, algorithm='custom', parent_manifest={'digest':'parent'},
                    cases_digest='cases', direction='improve', seed_score=0, validation_score=1,
                    metric_calls=1, snapshot=BasePromptTarget('original').snapshot(), config_path=str(config), profile_id='default')
            old = create('old'); latest = create('new')
            jobs = root / '.fruitfly/evolution'; jobs.mkdir()
            (jobs / 'job.json').write_text(json.dumps({'candidate_id':old.candidate_id}))
            self.assertEqual((), compact_candidates(root, store, config))
            self.assertEqual(2, len(store.list()))
            (jobs / 'job.json').unlink()
            sessions=root / '.fruitfly/sessions'; sessions.mkdir()
            (sessions / 'broken.jsonl').write_text('broken')
            self.assertEqual((), compact_candidates(root, store, config))
            self.assertEqual(2, len(store.list()))


class StartupVersionsTests(unittest.IsolatedAsyncioTestCase):
    async def setup_app(self, root):
        _write_models(root)
        provider = FauxProvider(); registry = Mock(); registry.create.return_value=provider
        factory = RunApplicationFactory(cwd=root, environment={'FRUITFLY_MODEL_PROFILE':'local'}, provider_registry=registry)
        factory.configuration.save(); factory.reload_configuration()
        app=AgentApplication(factory); await app.start()
        return app, factory, provider

    def candidate(self, app, factory, text='new guidance', target_id='base_prompt'):
        target=factory._current_targets[target_id]
        return factory.candidate_store.create(text=text, algorithm='custom', parent_manifest=app.runtime_manifest,
            cases_digest='cases', direction='improve', seed_score=0, validation_score=1, metric_calls=1,
            snapshot=target.snapshot(), config_path=str(factory.selection.config_path.resolve()), profile_id=factory.selection.profile.profile_id)

    async def test_latest_candidate_this_time_does_not_change_saved_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,factory,provider=await self.setup_app(Path(tmp))
            try:
                record=self.candidate(app,factory)
                service=RunStartupVersions(factory)
                token=next(v.token for v in service.versions(factory.configuration.snapshot()) if 'Latest' in v.label)
                original=factory.selection.profile.prompt
                handle=await service.prepare(app.runtime_manifest, (token,))
                await app.activate_runtime(handle, expected_manifest_digest=app.runtime_manifest['digest'])
                self.assertEqual(record.artifact_id, app.runtime_manifest['base_prompt']['reference'])
                self.assertEqual(original, factory._resolve().profile.prompt)
                self.assertEqual('proposed', factory.candidate_store.read(record.candidate_id).status)
                self.assertEqual([],provider.calls)
            finally: await app.close()

    async def test_failed_cancelled_and_empty_search_keep_latest_then_success_replaces_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            app,factory,provider=await self.setup_app(root)
            try:
                _write_cases(root)
                factory.configuration.set_mechanism('opro',enabled=True)
                factory.configuration.save(); await app.rebuild()
                old=self.candidate(app,factory,'previous pending')
                old=replace(old, task_pack_id='configured-cases', task_pack_name='Configured task cases')
                factory.candidate_store._write(old, create=False)
                from fruitfly_agent.run.task_results import save_task_result
                output = save_task_result(root, old, 'previous pending')
                for error in (RuntimeError('failed'),asyncio.CancelledError()):
                    with patch.object(factory._current_optimizer,'search',new=AsyncMock(side_effect=error)):
                        with self.assertRaises(type(error)):
                            await app.optimize('improve')
                    await asyncio.sleep(0)
                    self.assertEqual((old.candidate_id,),tuple(r.candidate_id for r in app.candidates()))
                    self.assertEqual('previous pending', (output / 'latest.txt').read_text())
                with patch.object(factory._current_optimizer,'search',new=AsyncMock(return_value=())):
                    self.assertEqual((),await app.optimize('improve'))
                self.assertEqual(old.candidate_id,app.candidates()[0].candidate_id)
                proposals=(TextProposal('first ranked','custom',validation_score=0.9),
                           TextProposal('second ranked','custom',validation_score=0.1))
                with patch.object(factory._current_optimizer,'search',new=AsyncMock(return_value=proposals)):
                    latest=await app.optimize('improve')
                self.assertEqual(1,len(latest))
                self.assertEqual('first ranked',factory.artifact_store.read_text(latest[0].artifact_id))
                self.assertEqual('first ranked', (output / 'latest.txt').read_text())
                self.assertEqual((latest[0].candidate_id,),tuple(r.candidate_id for r in app.candidates()))
                with self.assertRaises(ValueError): factory.candidate_store.read(old.candidate_id)
                self.assertEqual([],provider.calls)
            finally: await app.close()

    async def test_same_runtime_in_another_profile_cannot_adopt_this_profiles_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,factory,_=await self.setup_app(Path(tmp))
            try:
                record=self.candidate(app,factory)
                factory.candidate_store._write(replace(record,profile_id='other'),create=False)
                self.assertEqual((),app.candidates())
                with self.assertRaisesRegex(ValueError,'another configuration/profile'):
                    factory.candidate_profile(app.runtime_manifest,record.candidate_id)
            finally: await app.close()

    async def test_save_latest_default_and_restore_object_default_temporarily(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,factory,provider=await self.setup_app(Path(tmp))
            try:
                record=self.candidate(app,factory); service=RunStartupVersions(factory)
                token=next(v.token for v in service.versions(factory.configuration.snapshot()) if 'Latest' in v.label)
                handle=await service.prepare(app.runtime_manifest, (token,), remember=(token,))
                await app.activate_runtime(handle, expected_manifest_digest=app.runtime_manifest['digest'])
                self.assertEqual(record.artifact_id, factory._resolve().profile.prompt)
                self.assertEqual('adopted',factory.candidate_store.read(record.candidate_id).status)
                service=RunStartupVersions(factory)
                default=next(v.token for v in service.versions(factory.configuration.snapshot()) if 'default version' in v.label)
                handle=await service.prepare(app.runtime_manifest,(default,))
                await app.activate_runtime(handle, expected_manifest_digest=app.runtime_manifest['digest'])
                self.assertEqual('assistant-default',app.runtime_manifest['base_prompt']['reference'])
                self.assertEqual(record.artifact_id,factory._resolve().profile.prompt)
                self.assertEqual([],provider.calls)
            finally: await app.close()

    async def test_stale_candidate_startup_keeps_incumbent(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,factory,_=await self.setup_app(Path(tmp))
            try:
                record=self.candidate(app,factory)
                factory.candidate_store._write(replace(record,parent_manifest_digest='wrong'),create=False)
                service=RunStartupVersions(factory)
                token=next(v.token for v in service.versions(factory.configuration.snapshot()) if 'Latest' in v.label)
                before=app.runtime_manifest['digest']
                with self.assertRaisesRegex(ValueError,'stale'):
                    await service.prepare(app.runtime_manifest,(token,))
                self.assertEqual(before,app.runtime_manifest['digest'])
            finally: await app.close()

    async def test_skill_guidance_uses_same_startup_protocol_and_can_return_to_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,factory,provider=await self.setup_app(Path(tmp))
            try:
                factory.configuration.set_mechanism('skill-catalog',enabled=True)
                factory.configuration.save()
                await app.rebuild()
                record=self.candidate(app,factory,target_id='skill-catalog.guidance')
                service=RunStartupVersions(factory)
                latest=next(v.token for v in service.versions(factory.configuration.snapshot())
                            if v.target == 'skill-catalog.guidance' and 'Latest' in v.label)
                handle=await service.prepare(app.runtime_manifest,(latest,),remember=(latest,))
                await app.activate_runtime(handle,expected_manifest_digest=app.runtime_manifest['digest'])
                self.assertEqual(record.artifact_id,factory._resolve().profile.artifact_bindings['skill-catalog.guidance'])
                service=RunStartupVersions(factory)
                default=next(v.token for v in service.versions(factory.configuration.snapshot())
                             if v.target == 'skill-catalog.guidance' and 'default version' in v.label)
                handle=await service.prepare(app.runtime_manifest,(default,),remember=(default,))
                await app.activate_runtime(handle,expected_manifest_digest=app.runtime_manifest['digest'])
                self.assertNotIn('skill-catalog.guidance',factory._resolve().profile.artifact_bindings)
                service=RunStartupVersions(factory)
                accepted=next(v.token for v in service.versions(factory.configuration.snapshot())
                              if v.target == 'skill-catalog.guidance' and 'Latest accepted' in v.label)
                handle=await service.prepare(app.runtime_manifest,(accepted,))
                await app.activate_runtime(handle,expected_manifest_digest=app.runtime_manifest['digest'])
                self.assertEqual(record.artifact_id, next(a['id'] for a in app.runtime_manifest['data_artifacts']
                                                         if a['key'] == 'skill-catalog.guidance'))
                self.assertNotIn('skill-catalog.guidance',factory._resolve().profile.artifact_bindings)
                self.assertEqual([],provider.calls)
            finally: await app.close()

    async def test_structured_review_keeps_full_text_and_diff_lines_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,factory,_=await self.setup_app(Path(tmp))
            try:
                record=self.candidate(app,factory,'replacement without newline')
                view,diff=app.candidate_detail(record.candidate_id)
                sections={s.title:s.text for s in view.sections}
                self.assertEqual('replacement without newline',sections['Candidate text'])
                self.assertIn('\n+replacement',diff)
                self.assertIn('not provided',sections['Evaluation'])
                self.assertIn(str(factory.selection.config_path),sections['Scope'])
                self.assertEqual(diff, sections['Changes'])
                self.assertIn('unknown', sections['Search usage'])
                record = replace(record, report=asdict(SearchReport(
                    train_count=8, validation_count=4, baseline_train_score=.875, candidate_train_score=.875,
                    baseline_validation_score=1., candidate_validation_score=1.,
                    baseline_train_completed=8, candidate_train_completed=8,
                    baseline_validation_completed=4, candidate_validation_completed=4,
                    conclusion='tied', stop_reason='budget_exhausted', exhausted_kind='trial',
                    trial_calls=32, trial_limit=32, model_calls=33, model_limit=64,
                    tokens=TokenUsage(input_tokens=100, output_tokens=20, reported_calls=32, missing_calls=1))))
                (factory.candidate_store.root / f'{record.candidate_id}.json').write_text(json.dumps(asdict(record)))
                reviewed, _ = app.candidate_detail(record.candidate_id)
                summaries = '\n'.join(section.summary for section in reviewed.sections)
                self.assertIn('Tied; no measured improvement', summaries)
                self.assertIn('0.875 (8/8)', summaries)
                self.assertIn('1.0 (4/4)', summaries)
                self.assertIn('32/32', summaries)
                self.assertIn('Chat and manual testing remain available', summaries)
                self.assertIn('Reported tokens: 120', summaries)
                self.assertIn('actual total unknown', summaries)

            finally: await app.close()

    def test_startup_has_only_start_configure_exit(self):
        snapshot = SimpleNamespace(mechanisms=(), changed=False, ready=True,
            model_profile='local', prompt_label='Python adapted', selected_profile='default')
        for choice, starts in (('1', True), ('3', False)):
            output = io.StringIO()
            frontend = TerminalConfigurationFrontend(SimpleNamespace(snapshot=lambda: snapshot),
                input_stream=io.StringIO(choice + '\n'), output_stream=output)
            result = frontend.run()
            self.assertEqual(starts, result.start)
            self.assertEqual((), result.version_tokens)
            self.assertIn('2. Configure', output.getvalue())
            self.assertIn('3. Exit', output.getvalue())
            self.assertNotIn('▾', output.getvalue())
            self.assertNotIn('4. ', output.getvalue())

    def test_startup_ansi_exit_and_resume_do_not_save(self):
        snapshot = SimpleNamespace(mechanisms=(), changed=False, ready=True,
            model_profile='local', prompt_label='Default', selected_profile='default', warnings=())
        configuration = SimpleNamespace(snapshot=lambda: snapshot, save=Mock())
        sequence = iter((b'\x1b[B', b'\x1b[B', b'\r'))
        frontend = TerminalConfigurationFrontend(configuration, input_stream=io.StringIO(), output_stream=io.StringIO(),
            menu_input=SimpleNamespace(read_event=lambda: RawTerminalMenuInput.decode(next(sequence))))
        frontend.renderer.ansi = True
        self.assertFalse(frontend.run().start)
        configuration.save.assert_not_called()
        frontend.menu_input = SimpleNamespace(read_event=lambda: RawTerminalMenuInput.decode(b'\r'))
        self.assertTrue(frontend.run(editable=False).start)
        configuration.save.assert_not_called()

    def test_prompt_preview_paginates_and_requires_explicit_choice(self):
        sequence = iter((b'\x1b[6~', b'\x1b[A', b'\r'))
        output = io.StringIO()
        frontend = TerminalConfigurationFrontend(SimpleNamespace(), input_stream=io.StringIO(), output_stream=output,
            menu_input=SimpleNamespace(read_event=lambda: RawTerminalMenuInput.decode(next(sequence))))
        frontend.renderer.ansi = True
        self.assertEqual((False, 'Use for next session'),
                         frontend._preview_prompt('Python adapted', 'hash', '\n'.join(f'line {i}' for i in range(20))))
        self.assertIn('Review prompt (2/3)', output.getvalue())
        self.assertIn('> 2. Back', output.getvalue())
        self.assertIn('> 1. Use for next session', output.getvalue())

    async def test_candidate_section_switch_keeps_action_selection_and_full_text_pages(self):
        record=SimpleNamespace(candidate_id='candidate-1',status='proposed',algorithm='custom',target='target',
            evidence=(),sections=(CandidateSection('Overview','summary'),CandidateSection('Evaluation','score'),
                                 CandidateSection('Changes','diff',initial=True),CandidateSection('Original text','first\n'*20),
                                 CandidateSection('Candidate text','new')))
        session=SimpleNamespace(set_event_sink=Mock(),candidate_detail=lambda _: (record,'diff'),candidate_action=Mock())
        output=io.StringIO();frontend=TerminalFrontend(session,input_stream=io.StringIO(),output_stream=output)
        sequence=iter((b'\x1b[A',b'n',b'\x1b[6~',b'n',b'p',b'\x1b'))
        frontend.menu_input=SimpleNamespace(read_event=lambda:RawTerminalMenuInput.decode(next(sequence)))
        frontend.menu_renderer=TerminalMenuRenderer(output)
        frontend.menu_renderer.ansi=True
        await frontend._candidate_detail_flow('candidate-1')
        self.assertIn('Original text (2/3)',output.getvalue())
        self.assertIn('Candidate text (1/1)',output.getvalue())
        frames=[f for f in output.getvalue().split('\x1b[2J\x1b[H') if f.startswith('Candidate candidate-')]
        self.assertIn('> 4. Back',frames[0])
        self.assertTrue(all('> 3. Discard candidate' in f for f in frames[1:]))
        session.candidate_action.assert_not_called()
