"""Run services work with explicit capabilities and no composition Factory."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import AsyncMock

from fruitfly_agent.lab.algorithms.evolution import VerificationEvidence
from fruitfly_agent.lab.base_prompt.target import BasePromptTarget
from fruitfly_agent.lab.optimization.task_packs import TaskPackCatalog, TaskSnapshotStore
from fruitfly_agent.run.configuration.profile import HarnessProfile
from fruitfly_agent.run.configuration.model_setup import RunModelSetup
from fruitfly_agent.run.improvement.candidates import RunCandidates
from fruitfly_agent.run.improvement.evolution import RunEvolutionHost
from fruitfly_agent.run.improvement.search_jobs import RunSearchJobs
from fruitfly_agent.run.storage.artifacts import DataArtifactStore
from fruitfly_agent.run.storage.candidates import CandidateStore
from tests.support.materials import _write_cases
from tests.support.optimizers import OfflineOptimizer


class HostServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_owns_preview_receipts_and_runs_with_injected_capabilities(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            _write_cases(root)
            artifacts = DataArtifactStore(root / '.fruitfly/artifacts')
            candidates = CandidateStore(root / '.fruitfly/optimization/candidates', artifacts)
            target = BasePromptTarget('seed')
            optimizer = OfflineOptimizer('base_prompt')
            packs = TaskPackCatalog(root, legacy_path='.fruitfly/optimization/cases.json')
            manifest = SimpleNamespace(digest='parent', to_dict=lambda: {'digest': 'parent'})
            compactions = []
            jobs = RunSearchJobs(
                workspace=root, artifacts=artifacts, candidates=candidates,
                snapshots=TaskSnapshotStore(root), active_manifest=lambda: manifest,
                optimizer=lambda _manifest: optimizer,
                target=lambda _manifest, **_kwargs: target,
                task_catalog=lambda: packs, selected_target=lambda: 'base_prompt',
                scope=lambda: (str(root / 'config.yaml'), 'default'),
                compact=lambda: compactions.append(True),
            )
            preview = jobs.optimization_preview({'digest': 'parent'}, direction='improve')
            self.assertEqual(jobs.last_target('parent'), 'base_prompt')
            self.assertIsNone(jobs.last_target('another-parent'))
            records = await jobs.optimize({'digest': 'parent'}, 'improve', preview_token=preview.preview_token)
            self.assertEqual(len(records), 1)
            self.assertEqual(artifacts.read_text(records[0].artifact_id), 'seed\nUse exact answers.')
            self.assertEqual(optimizer.calls, 1)
            self.assertEqual(compactions, [True])
            with self.assertRaisesRegex(ValueError, 'consumed'):
                await jobs.optimize({'digest': 'parent'}, 'improve', preview_token=preview.preview_token)
            self.assertEqual(optimizer.calls, 1)
            jobs.clear()
            self.assertIsNone(jobs.last_target())

    async def test_candidate_activation_rechecks_settings_without_factory_or_application(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            artifacts = DataArtifactStore(root / 'artifacts')
            store = CandidateStore(root / 'candidates', artifacts)
            target = BasePromptTarget('seed')
            profile = HarnessProfile('default', 'models.yaml', 'offline')
            configuration = SimpleNamespace(changed=False)
            manifest = SimpleNamespace(digest='parent')
            record = store.create(
                text='candidate', algorithm='custom', parent_manifest={'digest': 'parent'},
                cases_digest='cases', direction='improve', seed_score=0, validation_score=1,
                metric_calls=1, snapshot=target.snapshot(),
                config_path=str(root / 'config.yaml'), profile_id='default',
            )
            activated = []
            handle = SimpleNamespace(manifest={'digest': 'child'}, activate_callback=lambda: activated.append(True))
            prepare = AsyncMock(return_value=handle)
            service = RunCandidates(
                workspace=root, store=store, artifacts=artifacts,
                scope=lambda: (str(root / 'config.yaml'), 'default'),
                profile=lambda: profile, resolved_profile=lambda: profile,
                configuration=lambda: configuration, active_manifest=lambda: manifest,
                active_profile=lambda: profile, target=lambda _identity: target,
                pinned_bindings={}, prepare_runtime=prepare, reload_configuration=lambda: None,
            )
            prepared = await service.prepare_candidate({'digest': 'parent'}, record.candidate_id)
            prepare.assert_awaited_once_with(replace(profile, prompt=record.artifact_id))
            self.assertIs(prepared, handle)
            self.assertEqual(store.read(record.candidate_id).status, 'proposed')
            configuration.changed = True
            with self.assertRaisesRegex(ValueError, 'configuration changed'):
                handle.activate_callback()
            self.assertEqual(activated, [])
            self.assertEqual(store.read(record.candidate_id).status, 'proposed')

    async def test_evolution_host_uses_only_its_injected_operations(self):
        with tempfile.TemporaryDirectory() as tmp:
            active = {'digest': 'parent'}
            record = SimpleNamespace(candidate_id='candidate', artifact_id='content',
                                     parent_manifest_digest='parent', activated_manifest_digest='')
            evidence = VerificationEvidence('candidate', 'content', 'parent', 'policy', True)
            prepare = AsyncMock(return_value='prepared-handle')
            calls = []

            async def activate(handle, *, expected_manifest_digest):
                calls.append((handle, expected_manifest_digest))
                active['digest'] = 'child'
                record.activated_manifest_digest = 'child'

            host = RunEvolutionHost(
                workspace=Path(tmp), manifest=lambda: active,
                propose=AsyncMock(return_value=(record,)),
                read_candidate=lambda _identity: record, read_artifact=lambda _identity: 'text',
                prepare_candidate=prepare, activate=activate,
                policy_id='policy', verify=AsyncMock(return_value=evidence),
            )
            self.assertEqual(await host.propose('improve'), 'candidate')
            self.assertEqual(await host.verify('candidate', 'policy'), evidence)
            outcome = await host.adopt('candidate', evidence)
            self.assertEqual((outcome.status, outcome.manifest_digest), ('activated', 'child'))
            self.assertEqual(calls, [('prepared-handle', 'parent')])
            self.assertTrue(host.is_active('candidate'))

    def test_model_setup_can_stage_and_roll_back_through_profile_callbacks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            profile = [HarnessProfile('default', 'models.yaml', None)]
            environment = {}
            setup = RunModelSetup(
                config_path=root / '.fruitfly/config.yaml', current_profile=lambda: profile[0],
                stage_profile=lambda value: profile.__setitem__(0, value),
                workspace=root, environment=environment,
            )
            setup.stage('openai', {
                'profile': 'offline', 'model': 'offline-model', 'base_url': '',
                'context_window': '8192', 'max_output_tokens': '1024', 'api_key_env': '',
            }, 'offline-placeholder')
            self.assertEqual(profile[0].model_profile, 'offline')
            self.assertFalse((root / '.fruitfly/models.yaml').exists())

            def fail():
                raise OSError('configuration persistence failed')

            with self.assertRaisesRegex(OSError, 'persistence failed'):
                setup.persist(fail)
            self.assertFalse((root / '.fruitfly/models.yaml').exists())
            self.assertFalse((root / '.fruitfly/secrets.env').exists())
            self.assertEqual(environment, {})
            self.assertTrue(setup.changed)
