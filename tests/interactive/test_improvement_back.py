"""The light chat entry keeps material editing and confirmation independent of experiments."""
from dataclasses import replace
import unittest
from tests.support.improvement_ui import panel


class WorkflowPanelTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_material_start_and_history_are_exposed(self):
        view, client, frames, _ = panel((None,))
        await view.run()
        self.assertEqual([row.label for row in frames[0][1]],
            ["Task", "Input files", "Start improvement", "Results and history"])
        self.assertEqual(view.request.strategy_id, "simple")
        self.assertFalse(view.request.retain_experience)
        self.assertEqual(view.request.component_ids, ())  # Host discovers legal material/backend targets.
        client.workflow_preview.assert_not_called()

    async def test_cancelled_material_input_keeps_previous_selection(self):
        view, client, _, _ = panel((0, 0, None), text=(None,))
        view.request = replace(view.request, task_pack_id="pack", direction="Keep citations")
        await view.run()
        self.assertEqual(view.request.task_pack_id, "pack")
        self.assertEqual(view.request.direction, "Keep citations")
        view.execute.assert_not_awaited()

    async def test_unavailable_material_explains_missing_capability(self):
        view, _, _, notices = panel((0, 1, None))
        view.configuration = replace(view.configuration, materials=(view.configuration.materials[0],
            replace(view.configuration.materials[1], available=False, reason="Material unavailable")))
        await view.run()
        self.assertEqual(view.request.task_pack_id, "")
        self.assertIn("Material unavailable", "".join(notices))

    async def test_input_files_preserve_values_after_invalid_input(self):
        view, _, _, notices = panel((1, 1, None), text=(chr(34), "input.txt"))
        await view.run()
        self.assertEqual(view.request.input_paths, ("input.txt",))
        self.assertTrue(notices)

    async def test_preview_and_confirmation_are_required_once(self):
        for confirmed in (False, True):
            with self.subTest(confirmed=confirmed):
                view, client, _, _ = panel((2, None), confirmed=confirmed)
                await view.run()
                client.workflow_preview.assert_called_once_with(view.request)
                view.confirm.assert_called_once()
                self.assertEqual(view.execute.await_count, int(confirmed))

    async def test_saved_material_owns_inputs(self):
        view, client, _, notices = panel((0, 1, 1, None))
        view.request = replace(view.request, input_paths=("old.txt",))
        await view.run()
        self.assertEqual(view.request.task_pack_id, "pack")
        self.assertEqual(view.request.input_paths, ())
        self.assertIn("owns", "".join(notices))
        client.workflow_preview.assert_not_called()

    async def test_failed_preview_retains_choices_without_starting_work(self):
        view, client, _, notices = panel((2, None))
        client.workflow_preview.side_effect = ValueError("Source changed")
        await view.run()
        self.assertIn("Source changed", "".join(notices))
        view.execute.assert_not_awaited()

    async def test_history_is_read_only_and_does_not_preview_or_start(self):
        view, client, _, _ = panel((3, None))
        await view.run()
        view.history.assert_awaited_once()
        client.workflow_preview.assert_not_called()
        view.execute.assert_not_awaited()
