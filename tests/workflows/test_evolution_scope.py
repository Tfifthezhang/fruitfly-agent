"""Host previews freeze policy parameters and observe independent jobs."""
from pathlib import Path
import tempfile
import unittest

from fruitfly_agent.interactive import AgentApplication
from fruitfly_agent.lab.improvement.termination import NoImprovement
from tests.support.improvers import offline_factory


class EvolutionScopeTests(unittest.IsolatedAsyncioTestCase):
    async def test_changed_stop_parameters_invalidate_preview_before_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            factory = offline_factory(Path(directory))
            factory._component_jobs.stop_policy = NoImprovement(2)
            app = AgentApplication(factory); await app.start()
            self.addAsyncCleanup(app.close)
            preview = app.workflow_preview(factory.test_request)
            factory._component_jobs.stop_policy = NoImprovement(3)
            with self.assertRaisesRegex(ValueError, 'conditions changed'):
                await app.improve('', preview_token=preview.preview_token)

    async def test_successive_jobs_have_separate_reports_and_cumulative_observations(self):
        with tempfile.TemporaryDirectory() as directory:
            factory=offline_factory(Path(directory));app=AgentApplication(factory);await app.start()
            self.addAsyncCleanup(app.close)
            totals=[]
            for _ in range(2):
                preview=app.workflow_preview(factory.test_request)
                await app.improve('',preview_token=preview.preview_token)
                totals.append(factory.improvement_usage()['execution'])
                self.assertEqual(factory._component_jobs.completion().report.trial_calls, 4)
            self.assertEqual(totals,[4,8])
            self.assertFalse(hasattr(factory,'improvement_budget_scope'))
