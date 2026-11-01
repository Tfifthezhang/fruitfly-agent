"""Task execution is an explicit port; no built-in reduced Agent is installed."""
import unittest
from types import SimpleNamespace
from pathlib import Path
import tempfile
from unittest.mock import Mock

from fruitfly_agent.lab.improvement.execution import builtin_executions
from fruitfly_agent.interactive import AgentApplication
from fruitfly_agent.interactive.contracts.improvement import WorkflowRequest
from fruitfly_agent.run import RunApplicationFactory
from tests.support.materials import _write_models
from tests.support.faux_provider import FauxProvider


class ExecutionRegistrationTests(unittest.IsolatedAsyncioTestCase):
    def test_removed_execution_is_not_registered_and_material_adapter_requires_a_runner(self):
        registry = builtin_executions()
        with self.assertRaisesRegex(ValueError, 'unknown execution'):
            registry.get('file-task')
        with self.assertRaisesRegex(ValueError, 'explicitly registered TaskRunner'):
            registry.get('agent-task').prepare(SimpleNamespace(runner_factory=None), None)
        from fruitfly_agent.experiments.task_sets import registry_for
        with self.assertRaisesRegex(ValueError, 'unknown task-set source'):
            registry_for(({'source': 'files'},)).get('files')
        options = registry.get('improver-comparison').materials(SimpleNamespace(runner_factory=None))
        self.assertTrue(options[0].error)

    async def test_ordinary_agent_starts_but_improvement_without_runner_makes_no_model_request(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_models(root)
            provider = FauxProvider()
            providers = Mock()
            providers.create.return_value = provider
            app = AgentApplication(RunApplicationFactory(cwd=root, environment={}, provider_registry=providers))
            await app.start()
            try:
                with self.assertRaisesRegex(ValueError, 'explicitly registered TaskRunner'):
                    app.workflow_preview(WorkflowRequest('Do a task.', component_ids=('base_prompt',)))
                self.assertEqual(provider.calls, [])
                provider.respond_text('ordinary chat still works')
                await app.submit('Hello')
                self.assertEqual(len(provider.calls), 1)
            finally:
                await app.close()
