"""Submitted experiments remain inspectable independently of candidate output."""
import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from fruitfly_agent.interactive import AgentApplication
from fruitfly_agent.run.adapters.improvement import RunImprovementService
from fruitfly_agent.run.storage.improvement_runs import ImprovementRunStore
from tests.support.application import open_task_app
from tests.support.task_packs import install


class ImprovementHistoryTests(unittest.IsolatedAsyncioTestCase):
    open_app = open_task_app

    async def test_preview_is_not_a_run_and_empty_search_retains_reason_baseline_and_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install(root)
            app, factory, provider = await self.open_app(root, 'opro')
            before = app.runtime_manifest
            preview = app.improvement_preview(pack_id='project', direction='Improve',
                method_id='opro', target_id='base_prompt', parameters={'rounds': 1, 'max_metric_calls': 2})
            self.assertEqual((), app.improvement_history())
            self.assertEqual([], provider.calls)
            provider.respond_text('B')
            provider.respond_text('A')
            # Proposal generation is authorized, but there are no remaining task trials.
            provider.respond_text('["candidate"]')
            self.assertEqual((), await app.improve('Improve', preview_token=preview.preview_token))
            row, = app.improvement_history()
            self.assertEqual((row.status, row.stop_reason), ('completed', 'budget_exhausted'))
            self.assertEqual(row.candidate_ids, ())
            sections = {s.title: s.text for s in row.sections}
            self.assertIn('Baseline selection: 1.0', sections['Evaluation'])
            self.assertIn('Task trials: 2/2', sections['Usage'])
            self.assertIn('budget_exhausted', app.improvement_run_logs(row.run_id))
            self.assertEqual(before, app.runtime_manifest)
            await app.close()
            restarted = AgentApplication(factory)
            await restarted.start()
            self.addAsyncCleanup(restarted.close)
            self.assertEqual(row, restarted.improvement_history()[0])

    async def test_failed_and_cancelled_jobs_persist_without_publishing_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install(root)
            app, factory, provider = await self.open_app(root, 'opro')
            for error, expected in ((RuntimeError('offline failure'), 'failed'),
                                    (asyncio.CancelledError(), 'cancelled')):
                preview = app.improvement_preview(pack_id='project', direction='Improve')
                with patch.object(factory._current_improver, 'search', new=AsyncMock(side_effect=error)):
                    with self.assertRaises(type(error)):
                        await app.improve('Improve', preview_token=preview.preview_token)
                self.assertEqual(expected, app.improvement_history()[0].status)
                self.assertEqual((), app.candidates())
                await asyncio.sleep(0)
            self.assertEqual(len(app.improvement_history()), 2)
            self.assertEqual([], provider.calls)

    async def test_history_preserves_candidate_artifacts_and_allows_reviewing_older_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install(root)
            app, factory, provider = await self.open_app(root, 'opro')
            records = []
            for text in ('first candidate', 'second candidate'):
                for response in ('wrong', 'wrong', f'["{text}"]', 'A', 'B'):
                    provider.respond_text(response)
                preview = app.improvement_preview(pack_id='project', direction='Improve', method_id='opro',
                    target_id='base_prompt', parameters={'rounds': 1, 'batch_size': 1})
                records.extend(await app.improve('Improve', preview_token=preview.preview_token))
            self.assertEqual(2, len(app.improvement_history()))
            self.assertEqual(2, len(factory.candidate_store.list()))
            view, diff = app.candidate_detail(records[0].candidate_id)
            self.assertIn('first candidate', diff)
            self.assertIn('selection', view.assessment)
            self.assertEqual(1, len(app.candidates()))
            await app.adopt_candidate(records[0].candidate_id)
            self.assertEqual(records[0].artifact_id, app.runtime_manifest['base_prompt']['reference'])

    async def test_abandoned_running_record_is_interrupted_without_replaying_work(self):
        from fruitfly_agent.interactive.contracts.improvement import ImprovementRunView
        with tempfile.TemporaryDirectory() as tmp:
            store = ImprovementRunStore(Path(tmp))
            store.save(ImprovementRunView('a' * 32, 'running'), ('config', 'profile'))
            service = RunImprovementService(jobs=None, activity=lambda: None, cancel=lambda: False,
                runs=store, scope=lambda: ('config', 'profile'))
            row, = service.improvement_history()
            self.assertEqual((row.status, row.stop_reason), ('interrupted', 'process_interrupted'))
            self.assertEqual((), row.candidate_ids)

    async def test_immediate_cancellation_records_the_submitted_experiment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install(root)
            app, _, provider = await self.open_app(root, 'opro')
            preview = app.improvement_preview(pack_id='project', direction='Improve')
            task = app.start_improvement('Improve', preview_token=preview.preview_token)
            app.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            row, = app.improvement_history()
            self.assertEqual((row.status, row.stop_reason), ('cancelled', 'cancelled_before_execution'))
            self.assertEqual([], provider.calls)
