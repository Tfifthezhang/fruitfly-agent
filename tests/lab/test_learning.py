"""Configured material timing, provenance and failure behavior."""
import asyncio
from dataclasses import replace
import unittest
from unittest.mock import AsyncMock

from fruitfly_agent.lab.learning import LearningEngine, LearningObservation, LearningMaterial, RecordingProcessor


class LearningTests(unittest.IsolatedAsyncioTestCase):
    def observation(self, identity='task'):
        return LearningObservation(identity, 'Question', 'Unverified answer', 'stop', 'manifest', 'session')

    async def test_recording_never_infers_ground_truth_from_agent_success(self):
        save = AsyncMock()
        engine = LearningEngine(processor=RecordingProcessor(), save=save)
        await engine.observe(self.observation())
        observation, material = save.await_args.args
        self.assertEqual(material.status, 'pending')
        self.assertEqual((material.acceptance, material.evidence), ('', ''))
        self.assertEqual(material.source_id, observation.source_id)

    async def test_session_batch_limits_deduplication_and_close(self):
        for trigger in ('session', 'batch'):
            with self.subTest(trigger=trigger):
                save = AsyncMock()
                engine = LearningEngine(processor=RecordingProcessor(), save=save, trigger=trigger, batch_size=2, max_records=3)
                self.assertTrue(await engine.observe(self.observation('a')))
                self.assertFalse(await engine.observe(self.observation('a')))
                save.assert_not_awaited()
                await engine.observe(self.observation('b'))
                self.assertEqual(save.await_count, 2 if trigger == 'batch' else 0)
                await engine.observe(self.observation('c'))
                self.assertFalse(await engine.observe(self.observation('d')))
                await engine.close()
                self.assertEqual(save.await_count, 3)

    async def test_processor_failure_keeps_pending_and_unattributed_material_rejects(self):
        save = AsyncMock()
        processor = RecordingProcessor()
        processor.process = AsyncMock(side_effect=RuntimeError('unavailable'))
        engine = LearningEngine(processor=processor, save=save)
        with self.assertRaises(RuntimeError):
            await engine.observe(self.observation())
        self.assertEqual(len(engine.pending), 1)
        save.assert_not_awaited()
        await engine.close()
        self.assertEqual(processor.process.await_count, 1)
        save.assert_not_awaited()
        processor.process.side_effect = None
        processor.process.return_value = LearningMaterial('wrong source', 'q', 'a')
        fresh = LearningEngine(processor=processor, save=save)
        with self.assertRaisesRegex(ValueError, 'attribution'):
            await fresh.observe(self.observation())
        save.assert_not_awaited()

    async def test_verified_material_requires_a_standard_and_evidence(self):
        with self.assertRaises(ValueError):
            LearningMaterial('task', 'question', 'answer', status='verified')
        save = AsyncMock()
        processor = RecordingProcessor()
        processor.process = AsyncMock(return_value=LearningMaterial('task', 'question', 'answer', 'verified', 'executable check', 'verifier receipt'))
        engine = LearningEngine(processor=processor, save=save)
        await engine.observe(self.observation())
        self.assertEqual(save.await_args.args[1].status, 'verified')

    async def test_oversized_observation_is_not_silently_truncated(self):
        engine = LearningEngine(processor=RecordingProcessor(), save=AsyncMock(), max_chars=5)
        self.assertFalse(await engine.observe(self.observation()))
        self.assertEqual(engine.pending, [])

    async def test_persistence_retry_reuses_processed_material_without_model_replay(self):
        save = AsyncMock(side_effect=[OSError('write failed'), None])
        processor = RecordingProcessor()
        processor.process = AsyncMock(wraps=processor.process)
        engine = LearningEngine(processor=processor, save=save)
        with self.assertRaises(OSError):
            await engine.observe(self.observation())
        await engine.close()
        self.assertEqual(processor.process.await_count, 1)
        self.assertEqual(save.await_count, 2)
