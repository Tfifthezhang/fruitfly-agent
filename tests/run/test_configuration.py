from __future__ import annotations


from dataclasses import replace



import tempfile
import unittest
from pathlib import Path






from fruitfly_agent.lab.catalog import builtin_catalog
from fruitfly_agent.run.configuration import load_harness_config
from fruitfly_agent.run import DataArtifactStore, RunConfigurationController, resolve_harness_selection






from tests.support.run import _write_catalog


class HarnessSelectionTest(unittest.TestCase):
    def test_selection_group_projects_and_applies_as_one_draft_operation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_catalog(root / "models.yaml", {"only": "model-a"})
            catalog = builtin_catalog()
            selected = resolve_harness_selection(
                cwd=root, config_path=None, profile_id=None,
                environment={}, catalog=catalog, allow_incomplete=True,
            )
            controller = RunConfigurationController(selected, catalog)
            reduction = next(item for item in controller.snapshot().selection_groups
                             if item.group_id == "reduction")
            self.assertEqual(reduction.option_ids, ("compaction",))
            self.assertEqual(reduction.selected_id, "compaction")
            self.assertEqual(reduction.label, "Reduction")
            group = next(item for item in controller.snapshot().selection_groups
                         if item.group_id == "text-optimizer")
            self.assertEqual(group.option_ids, ("opro",))
            controller.select_algorithm("text-optimizer", "opro")
            selected_group = next(item for item in controller.snapshot().selection_groups
                                  if item.group_id == "text-optimizer")
            self.assertEqual(selected_group.selected_id, "opro")
            controller.select_algorithm("text-optimizer", None)
            disabled_group = next(item for item in controller.snapshot().selection_groups
                                  if item.group_id == "text-optimizer")
            self.assertIsNone(disabled_group.selected_id)

    def test_reduction_group_accepts_another_algorithm_without_frontend_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_catalog(root / "models.yaml", {"only": "model-a"})
            original = builtin_catalog()
            summarizing = original.get("compaction")
            alternative = replace(summarizing, descriptor=replace(
                summarizing.descriptor, mechanism_id="alternative-reducer",
                label="Alternative reducer", default_enabled=False,
            ))
            catalog = original.extended((alternative,))
            selected = resolve_harness_selection(
                cwd=root, config_path=None, profile_id=None, environment={},
                catalog=catalog, allow_incomplete=True,
            )
            controller = RunConfigurationController(selected, catalog)
            controller.select_algorithm("reduction", "alternative-reducer")
            group = next(item for item in controller.snapshot().selection_groups
                         if item.group_id == "reduction")
            self.assertEqual(set(group.option_ids), {"compaction", "alternative-reducer"})
            self.assertEqual(group.selected_id, "alternative-reducer")
            self.assertFalse(next(item for item in controller.snapshot().mechanisms
                                  if item.mechanism_id == "compaction").enabled)

    def test_prompt_choice_is_staged_and_persisted_for_next_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_catalog(root / "models.yaml", {"local": "model-a"})
            catalog = builtin_catalog()
            selection = resolve_harness_selection(
                cwd=root, config_path=None, profile_id=None,
                environment={}, catalog=catalog,
            )
            store = DataArtifactStore(root / ".fruitfly" / "artifacts")
            ref = store.put_text("Research candidate")
            controller = RunConfigurationController(selection, catalog, store)
            self.assertEqual(controller.snapshot().prompt_reference, "assistant-default")
            self.assertNotIn(ref.artifact_id, controller.snapshot().prompt_options)
            self.assertEqual(controller.preview_prompt(ref.artifact_id)[2], "Research candidate")
            controller.select_prompt(ref.artifact_id)
            self.assertEqual(controller.snapshot().prompt_reference, ref.artifact_id)
            self.assertIn(ref.artifact_id, controller.snapshot().prompt_options)
            self.assertEqual(selection.profile.prompt, "assistant-default")
            controller.save()
            self.assertEqual(load_harness_config(selection.config_path).select().prompt, ref.artifact_id)
            with self.assertRaises(ValueError):
                controller.select_prompt("sha256:invalid")

    def test_compaction_effects_follow_the_selected_algorithm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_catalog(root / "models.yaml", {"local": "model-a"})
            catalog = builtin_catalog()
            selected = resolve_harness_selection(
                cwd=root,
                config_path=None,
                profile_id=None,
                environment={},
                catalog=catalog,
            )
            controller = RunConfigurationController(selected, catalog)

            summarizing = next(
                item for item in controller.snapshot().mechanisms
                if item.mechanism_id == "compaction"
            )
            with self.assertRaises(ValueError):
                controller.set_parameter("compaction", "profile", "window")

        self.assertIn("uses an auxiliary Provider", summarizing.effects)
        self.assertTrue(any("may incur Provider charges" in row for row in summarizing.effects))

    def test_sole_model_synthesizes_documented_catalog_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model_path = root / "models.yaml"
            _write_catalog(model_path, {"local": "model-a"})

            selected = resolve_harness_selection(
                cwd=root,
                config_path=None,
                profile_id=None,
                environment={},
                catalog=builtin_catalog(),
            )

        self.assertFalse(selected.persisted)
        self.assertEqual(selected.profile.model_profile, "local")
        self.assertEqual(selected.profile.model_catalog, "../models.yaml")
        self.assertEqual(
            selected.config_path,
            (root / ".fruitfly" / "config.yaml").resolve(),
        )
        self.assertEqual(
            {item.mechanism_id for item in selected.profile.mechanisms},
            {
                "local-env",
                "read-tool",
                "bash-tool",
                "edit-tool",
                "write-tool",
                "skill-catalog",
                "information-context",
                "memory-files",
                "compaction",
            },
        )

    def test_ambiguous_model_can_enter_provider_free_setup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_catalog(root / "models.yaml", {"a": "model-a", "b": "model-b"})
            selected = resolve_harness_selection(
                cwd=root,
                config_path=None,
                profile_id=None,
                environment={},
                catalog=builtin_catalog(),
                allow_incomplete=True,
            )

        self.assertIsNone(selected.profile.model_profile)

    def test_controller_saves_only_profile_state_for_a_future_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_catalog(root / "models.yaml", {"a": "model-a", "b": "model-b"})
            catalog = builtin_catalog()
            selected = resolve_harness_selection(
                cwd=root,
                config_path=None,
                profile_id=None,
                environment={},
                catalog=catalog,
                allow_incomplete=True,
            )
            controller = RunConfigurationController(selected, catalog)

            controller.select_model("b")
            controller.set_mechanism("knowledge-files", enabled=True)
            controller.set_mechanism("skill-catalog", enabled=True)
            before = controller.snapshot()
            result = controller.save()
            persisted = load_harness_config(root / ".fruitfly" / "config.yaml")

        self.assertTrue(before.changed)
        self.assertTrue(result.saved)
        self.assertIn("newly created session", result.message)
        self.assertEqual(persisted.select().model_profile, "b")
        self.assertIn(
            "knowledge-files",
            {
                item.mechanism_id
                for item in persisted.select().mechanisms
                if item.enabled
            },
        )
        enabled = {
            item.mechanism_id
            for item in persisted.select().mechanisms
            if item.enabled
        }
        self.assertIn("skill-catalog", enabled)

    def test_synthesized_configuration_is_saved_to_the_hidden_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_catalog(root / "models.yaml", {"only": "model-a"})
            catalog = builtin_catalog()
            selected = resolve_harness_selection(
                cwd=root,
                config_path=None,
                profile_id=None,
                environment={},
                catalog=catalog,
            )
            controller = RunConfigurationController(selected, catalog)

            self.assertTrue(controller.snapshot().changed)
            result = controller.save()
            persisted = load_harness_config(
                root / ".fruitfly" / "config.yaml"
            )

        self.assertTrue(result.saved)
        self.assertEqual(persisted.select().model_profile, "only")
        self.assertEqual(persisted.select().model_catalog, "../models.yaml")

    def test_disabling_a_requirement_disables_dependent_mechanisms(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_catalog(root / "models.yaml", {"only": "model-a"})
            catalog = builtin_catalog()
            selected = resolve_harness_selection(
                cwd=root,
                config_path=None,
                profile_id=None,
                environment={},
                catalog=catalog,
            )
            controller = RunConfigurationController(selected, catalog)

            controller.set_mechanism("local-env", enabled=False)
            enabled = {
                item.mechanism_id
                for item in controller.snapshot().mechanisms
                if item.enabled
            }

        self.assertNotIn("local-env", enabled)
        self.assertTrue(
            {
                "read-tool",
                "bash-tool",
                "edit-tool",
                "write-tool",
            }.isdisjoint(enabled)
        )

    def test_controller_can_choose_a_nondefault_model_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog_dir = root / "configs"
            catalog_dir.mkdir()
            _write_catalog(catalog_dir / "models.yaml", {"only": "model-a"})
            catalog = builtin_catalog()
            selected = resolve_harness_selection(
                cwd=root,
                config_path=None,
                profile_id=None,
                environment={},
                catalog=catalog,
                allow_incomplete=True,
            )
            controller = RunConfigurationController(selected, catalog)

            controller.select_model_catalog("../configs/models.yaml")
            snapshot = controller.snapshot()

        self.assertEqual(snapshot.model_catalog, "../configs/models.yaml")
        self.assertEqual(snapshot.model_profile, "only")
        self.assertEqual(snapshot.model_profiles, ("only",))

    def test_controller_exposes_and_enables_rlm_through_generic_configuration(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_catalog(root / "models.yaml", {"only": "model-a"})
            catalog = builtin_catalog()
            selected = resolve_harness_selection(
                cwd=root,
                config_path=None,
                profile_id=None,
                environment={},
                catalog=catalog,
            )
            controller = RunConfigurationController(selected, catalog)

            before = next(
                item
                for item in controller.snapshot().mechanisms
                if item.mechanism_id == "rlm-ipython"
            )
            controller.set_mechanism("rlm-ipython", enabled=True)
            after = next(
                item
                for item in controller.snapshot().mechanisms
                if item.mechanism_id == "rlm-ipython"
            )
            context_items = [
                item
                for item in controller.snapshot().mechanisms
                if item.category == "context-manager" and item.visible
            ]
            information_context = next(
                item for item in controller.snapshot().mechanisms
                if item.mechanism_id == "information-context"
            )
            tool = next(
                item for item in controller.snapshot().mechanisms
                if item.mechanism_id == "ipython-tool"
            )

        self.assertEqual("context-manager", before.category)
        self.assertEqual("online", before.layer)
        self.assertEqual("context", before.family)
        self.assertEqual("externalization", before.context_phase)
        self.assertEqual(
            ["augmentation", "augmentation", "augmentation", "augmentation", "externalization", "reduction"],
            [item.display_section for item in context_items],
        )
        self.assertEqual(
            {"skill-catalog", "memory-files", "knowledge-files", "live-http"},
            {
                item.mechanism_id
                for item in context_items
                if item.display_section == "augmentation"
            },
        )
        self.assertFalse(information_context.visible)
        self.assertFalse(before.enabled)
        self.assertTrue(after.enabled)
        self.assertTrue(tool.enabled)
        self.assertEqual("tools", tool.category)
        self.assertIn("adds tools: ipython", tool.effects)

    def test_disabling_ipython_tool_disables_dependent_externalization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_catalog(root / "models.yaml", {"only": "model-a"})
            catalog = builtin_catalog()
            selected = resolve_harness_selection(
                cwd=root, config_path=None, profile_id=None,
                environment={}, catalog=catalog,
            )
            controller = RunConfigurationController(selected, catalog)
            controller.set_mechanism("rlm-ipython", enabled=True)
            controller.set_mechanism("ipython-tool", enabled=False)
            enabled = {
                item.mechanism_id: item.enabled
                for item in controller.snapshot().mechanisms
            }
            self.assertFalse(enabled["ipython-tool"])
            self.assertFalse(enabled["rlm-ipython"])

    def test_controller_snapshot_reloads_the_tracked_model_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model_path = root / "models.yaml"
            _write_catalog(model_path, {"first": "model-a"})
            catalog = builtin_catalog()
            selected = resolve_harness_selection(
                cwd=root,
                config_path=None,
                profile_id=None,
                environment={},
                catalog=catalog,
            )
            controller = RunConfigurationController(selected, catalog)

            self.assertEqual(controller.snapshot().model_profiles, ("first",))
            _write_catalog(
                model_path,
                {"first": "model-a", "second": "model-b"},
            )

            self.assertEqual(
                controller.snapshot().model_profiles,
                ("first", "second"),
            )
