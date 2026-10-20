"""Workflow intent, failed work and immutable journals survive session changes."""
import asyncio
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
from fruitfly_agent.interactive import AgentApplication
from fruitfly_agent.interactive.contracts.improvement import ImprovementRunView
from fruitfly_agent.run.adapters.improvement import RunImprovementService
from fruitfly_agent.run.storage.improvement_runs import ImprovementRunStore
from tests.support.improvers import offline_factory, improve


class ImprovementHistoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_preview_is_offline_and_logs_are_hash_checked_after_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            factory = offline_factory(Path(tmp))
            app = AgentApplication(factory)
            await app.start()
            preview = app.workflow_preview(factory.test_request)
            self.assertEqual(app.improvement_history(), ())
            await app.improve('', preview_token=preview.preview_token)
            row, = app.improvement_history()
            self.assertEqual(row.status, 'completed')
            self.assertIn('execution-start', app.improvement_run_logs(row.run_id))
            await app.close()
            await app.start()
            try:
                self.assertEqual(app.improvement_history()[0], row)
                journal = factory.cwd / dict(row.evidence)['Workflow journal']
                journal.write_text('tampered')
                with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                    app.improvement_run_logs(row.run_id)
            finally:
                await app.close()

    async def test_failed_and_cancelled_jobs_keep_history_without_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            factory = offline_factory(Path(tmp))
            app = AgentApplication(factory)
            await app.start()
            try:
                for error, status in ((RuntimeError('offline failure'), 'failed'), (asyncio.CancelledError(), 'cancelled')):
                    preview = app.workflow_preview(factory.test_request)
                    with patch.object(factory._component_jobs.generators.factories['offline-rule'], 'propose', new=AsyncMock(side_effect=error)):
                        with self.assertRaises(type(error)):
                            await app.improve('', preview_token=preview.preview_token)
                    self.assertEqual(app.improvement_history()[0].status, status)
                    self.assertFalse(app.candidates())
                    await asyncio.sleep(0)
                self.assertEqual(len(app.improvement_history()), 2)
            finally:
                await app.close()

    async def test_immediate_cancel_records_intent_without_running_a_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            factory = offline_factory(Path(tmp))
            app = AgentApplication(factory)
            await app.start()
            try:
                preview = app.workflow_preview(factory.test_request)
                task = app.start_improvement('', preview_token=preview.preview_token)
                app.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                row, = app.improvement_history()
                self.assertEqual((row.status, row.stop_reason), ('cancelled', 'cancelled_before_execution'))
            finally:
                await app.close()

    async def test_abandoned_record_is_interrupted_without_replaying_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ImprovementRunStore(Path(tmp))
            store.save(ImprovementRunView('a' * 32, 'running'), ('config', 'profile'))
            service = RunImprovementService(jobs=None, activity=lambda: None, cancel=lambda: False,
                runs=store, scope=lambda: ('config', 'profile'))
            row, = service.improvement_history()
            self.assertEqual((row.status, row.stop_reason), ('interrupted', 'process_interrupted'))
