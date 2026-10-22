"""Workflow navigation keeps job choices and never starts work implicitly."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, AsyncMock
from fruitfly_agent.interactive.contracts.improvement import (ImprovementPreview,
    WorkflowExecutionView, WorkflowChoice, ImprovementParameterView)
from fruitfly_agent.interactive.terminal.features.improvement.workflow_panel import WorkflowPanel
from tests.support.improvement_ui import configuration, panel


class WorkflowPanelTests(unittest.IsolatedAsyncioTestCase):
    panel = staticmethod(panel)

    async def test_registered_execution_changes_components_materials_and_typed_parameters(self):
        view = WorkflowExecutionView('custom-experiment', 'Custom experiment', ('editor',),
            (WorkflowChoice('study', 'Independent study'),),
            (ImprovementParameterView('repeats', 'Repeated trials', 'integer', 2, 2, 10),),
            'Explicit model work', defaults=(('verification', 'scored'), ('scope', 'persistent')))
        panel, client, _, _ = self.panel((11, 0, 0, 0, 12, 0, None, None), text=('3',))
        panel.executions = (view,)
        await panel.run()
        self.assertEqual(panel.request.execution_id, 'custom-experiment')
        self.assertEqual(panel.request.component_ids, ('editor',))
        self.assertEqual(panel.request.task_pack_id, 'study')
        self.assertEqual(panel.request.execution_parameters, (('repeats', 3),))
        self.assertEqual((panel.request.verification, panel.request.scope), ('scored', 'persistent'))
        self.assertTrue(next(c for c in panel.configuration.components if c.component_id == 'editor').available)
        client.workflow_preview.assert_not_called()
        panel.execute.assert_not_awaited()

    async def test_back_keeps_component_selection_and_guidance(self):
        panel, client, frames, _ = self.panel((2, 1, None, 8, None), text=('Keep citations',))
        await panel.run()
        self.assertEqual(panel.request.component_ids, ('base_prompt', 'memory'))
        self.assertEqual(panel.request.direction, 'Keep citations')
        client.workflow_preview.assert_not_called()
        panel.execute.assert_not_awaited()

    async def test_unavailable_component_explains_missing_capability(self):
        panel, _, _, notices = self.panel((2, 2, None, None))
        await panel.run()
        self.assertEqual(panel.request.component_ids, ('base_prompt',))
        self.assertIn('Comparison runner required', ''.join(notices))

    async def test_allocations_preserve_values_after_invalid_input(self):
        panel, _, _, notices = self.panel((5, 0, 5, 0, None, None), text=('10001', '8'))
        await panel.run()
        self.assertEqual(panel.request.max_model_calls, 8)
        self.assertIn('outside', ''.join(notices))

    async def test_preview_and_confirmation_are_required_once(self):
        for confirmed in (False, True):
            with self.subTest(confirmed=confirmed):
                panel, client, _, _ = self.panel((9, None), confirmed=confirmed)
                await panel.run()
                client.workflow_preview.assert_called_once_with(panel.request)
                panel.confirm.assert_called_once()
                self.assertEqual(panel.execute.await_count, int(confirmed))

    async def test_generator_mode_and_saved_material_are_independent(self):
        panel, _, _, _ = self.panel((3, 1, 4, 1, None, 0, 1, None))
        await panel.run()
        self.assertEqual((panel.request.generator_id, panel.request.mode, panel.request.task_pack_id), ('agent', 'sequential', 'pack'))
        panel.execute.assert_not_awaited()

    async def test_failed_preview_retains_choices_without_starting_work(self):
        panel, client, _, notices = self.panel((9, None))
        client.workflow_preview.side_effect = ValueError('Source changed')
        await panel.run()
        self.assertIn('Source changed', ''.join(notices))
        panel.execute.assert_not_awaited()
