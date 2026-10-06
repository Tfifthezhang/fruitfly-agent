"""Explicit RSI policy over the same candidate host and real runtime activation."""
import asyncio
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from fruitfly_agent.interactive import AgentApplication
from fruitfly_agent.lab.algorithms.evolution import VerificationEvidence
from fruitfly_agent.lab.rsi.persistent import PersistentEvolutionDriver
from fruitfly_agent.run.evolution import RunEvolutionHost
from fruitfly_agent.run.application import RunApplicationFactory
from tests.support.optimizers import offline_factory


class PersistentEvolutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_two_activations_rebind_improver_and_job_survives_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            factory = offline_factory(Path(tmp))
            app = AgentApplication(factory)
            await app.start()
            observed = []
            async def verify(record, text):
                observed.append((record.parent_manifest_digest, text, record.artifact_id))
                return VerificationEvidence(record.candidate_id, record.artifact_id, record.parent_manifest_digest, 'explicit-policy', True)
            host = RunEvolutionHost(app, factory, policy_id='explicit-policy', verify=verify)
            first_optimizer = factory._current_optimizer
            result = await PersistentEvolutionDriver().evolve(host, job_id='job', policy_id='explicit-policy', direction='improve', max_steps=2)
            self.assertEqual(result.phase, 'complete')
            self.assertEqual(result.steps, 2)
            self.assertEqual(len(observed), 2)
            self.assertNotEqual(observed[0][0], observed[1][0])
            self.assertIsNot(first_optimizer, factory._current_optimizer)
            self.assertEqual(first_optimizer.calls, 1)
            self.assertEqual(factory._current_optimizer.calls, 0)
            self.assertEqual(host.active_manifest(), result.current_manifest)
            self.assertEqual(len(factory.candidate_store.list()), 1)
            self.assertEqual(factory.artifact_store.read_text(observed[0][2]), observed[0][1])
            await app.close()
            fresh_factory = RunApplicationFactory(cwd=Path(tmp), environment={}, catalog=factory.catalog, provider_registry=factory.provider_registry)
            restored = AgentApplication(fresh_factory)
            await restored.start()
            new_host = RunEvolutionHost(restored, fresh_factory, policy_id='explicit-policy', verify=verify)
            resumed = await PersistentEvolutionDriver().evolve(new_host, job_id='job', policy_id='explicit-policy', direction='improve', max_steps=2)
            self.assertEqual(resumed, result)
            self.assertEqual(len(observed), 2)
            await restored.close()

    async def test_planned_selection_does_not_count_as_activation(self):
        with tempfile.TemporaryDirectory() as tmp:
            factory = offline_factory(Path(tmp))
            app = AgentApplication(factory)
            await app.start()
            records = await app.optimize('improve')
            before = app.runtime_manifest
            app.candidate_action(records[0].candidate_id, 'adopt')
            host = RunEvolutionHost(app, factory, policy_id='policy', verify=lambda *args: None)
            self.assertFalse(host.is_active(records[0].candidate_id))
            self.assertEqual(app.runtime_manifest, before)
            await app.close()

    async def test_crash_after_activation_is_reconciled_without_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            factory = offline_factory(Path(tmp))
            app = AgentApplication(factory)
            await app.start()
            async def verify(record, text):
                return VerificationEvidence(record.candidate_id, record.artifact_id, record.parent_manifest_digest, 'policy', True)
            host = RunEvolutionHost(app, factory, policy_id='policy', verify=verify)
            original = host.save_job
            def crash(job):
                if job.phase == 'ready' and job.steps == 1:
                    raise RuntimeError('crash after activation')
                original(job)
            host.save_job = crash
            with self.assertRaisesRegex(RuntimeError, 'crash after activation'):
                await PersistentEvolutionDriver().evolve(host, job_id='crash', policy_id='policy', direction='improve', max_steps=1)
            self.assertEqual(host.load_job('crash').phase, 'activating')
            host.save_job = original
            resumed = await PersistentEvolutionDriver().evolve(host, job_id='crash', policy_id='policy', direction='improve', max_steps=1)
            self.assertEqual(resumed.phase, 'complete')
            self.assertEqual(len(app.candidates()), 1)
            await app.close()

    async def test_wrong_evidence_never_activates(self):
        with tempfile.TemporaryDirectory() as tmp:
            factory = offline_factory(Path(tmp))
            app = AgentApplication(factory)
            await app.start()
            async def wrong(record, text):
                return VerificationEvidence(record.candidate_id, 'sha256:wrong', record.parent_manifest_digest, 'policy', True)
            host = RunEvolutionHost(app, factory, policy_id='policy', verify=wrong)
            before = app.runtime_manifest
            with self.assertRaisesRegex(ValueError, 'exact candidate'):
                await PersistentEvolutionDriver().evolve(host, job_id='wrong', policy_id='policy', direction='improve')
            self.assertEqual(app.runtime_manifest, before)
            await app.close()

    async def test_uncertain_proposal_is_not_replayed_after_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            factory = offline_factory(Path(tmp))
            app = AgentApplication(factory)
            await app.start()
            host = RunEvolutionHost(app, factory, policy_id='policy', verify=lambda *_: None)
            async def fail(direction):
                raise RuntimeError('proposal interrupted')
            host.propose = fail
            driver = PersistentEvolutionDriver()
            with self.assertRaisesRegex(RuntimeError, 'proposal interrupted'):
                await driver.evolve(host, job_id='interrupted', policy_id='policy', direction='improve')
            fresh_host = RunEvolutionHost(app, factory, policy_id='policy', verify=lambda *_: None)
            result = await driver.evolve(fresh_host, job_id='interrupted', policy_id='policy', direction='improve')
            self.assertEqual(result.phase, 'interrupted')
            self.assertEqual(result.steps, 1)
            self.assertEqual(factory._current_optimizer.calls, 0)
            await app.close()

    async def test_configuration_change_after_prepare_is_not_overwritten_by_activation(self):
        with tempfile.TemporaryDirectory() as tmp:
            factory = offline_factory(Path(tmp))
            app = AgentApplication(factory)
            await app.start()
            self.addAsyncCleanup(app.close)
            before = app.runtime_manifest
            record = (await app.optimize('improve'))[0]
            candidate = await factory.prepare_candidate(before, record.candidate_id)
            factory.configuration.set_mechanism('knowledge-files', enabled=True)
            factory.configuration.save()
            with self.assertRaisesRegex(ValueError, 'configuration changed while preparing'):
                await app.activate_runtime(candidate, expected_manifest_digest=before['digest'])
            self.assertEqual(app.runtime_manifest, before)
            items = {item.mechanism_id: item for item in factory.configuration.snapshot().mechanisms}
            self.assertTrue(items['knowledge-files'].enabled)
            self.assertEqual(factory.candidate_store.read(record.candidate_id).status, 'proposed')
