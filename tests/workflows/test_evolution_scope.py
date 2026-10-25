"""Host previews freeze policy parameters and share a declared root allowance."""
from pathlib import Path
import tempfile
import unittest

from fruitfly_agent.interactive import AgentApplication
from fruitfly_agent.lab.improvement.api import NoImprovement, BudgetScope
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

    async def test_host_jobs_charge_the_common_root_and_return_unused_quota(self):
        with tempfile.TemporaryDirectory() as directory:
            factory = offline_factory(Path(directory))
            app = AgentApplication(factory); await app.start()
            self.addAsyncCleanup(app.close)
            root = BudgetScope({'model': 64, 'execution': 32})
            for index in range(2):
                with factory.improvement_budget_scope(root):
                    preview = app.workflow_preview(factory.test_request)
                    await app.improve('', preview_token=preview.preview_token)
                self.assertGreater(root.used['execution'], 0)
                self.assertEqual(root.held, {'model': 0, 'execution': 0})
            self.assertEqual(root.used['execution'], 8)
