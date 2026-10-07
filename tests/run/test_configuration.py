from __future__ import annotations


from dataclasses import replace


import tempfile
import unittest
from pathlib import Path


from fruitfly_agent.lab.catalog import MechanismSelection, builtin_catalog
from fruitfly_agent.run.configuration import load_harness_config
from fruitfly_agent.run import DataArtifactStore, RunConfigurationController, resolve_harness_selection


from tests.support.run import _write_catalog


class HarnessSelectionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def selection(self, *, catalog=None, environment=None, **kwargs):
        return resolve_harness_selection(
            cwd=self.root, config_path=None, profile_id=None, environment=environment or {},
            catalog=catalog if catalog is not None else builtin_catalog(), **kwargs,
        )

    def test_parameter_edit_does_not_silently_repair_duplicate_selections(self) -> None:
        root = self.root
        _write_catalog(root / "models.yaml", {"local": "model-a"})
        catalog = builtin_catalog()
        selection = self.selection(catalog=catalog)
        parameter = next(item for item in catalog.get("compaction").descriptor.parameters
                         if item.kind == "number")
        profile = replace(selection.profile, mechanisms=(
            MechanismSelection("compaction", enabled=False),
            MechanismSelection("compaction", enabled=True),
        ))
        selection = replace(selection, profile=profile,
                            config=replace(selection.config, profiles={profile.profile_id: profile}))
        controller = RunConfigurationController(selection, catalog)
        controller.set_parameter("compaction", parameter.name, str(parameter.default))
        with self.assertRaisesRegex(ValueError, "duplicate mechanism selection"):
            controller.save()

    def test_selection_group_projects_and_applies_as_one_draft_operation(self) -> None:
        root = self.root
        _write_catalog(root / "models.yaml", {"only": "model-a"})
        catalog = builtin_catalog()
        selected = self.selection(catalog=catalog, allow_incomplete=True)
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
        root = self.root
        _write_catalog(root / "models.yaml", {"only": "model-a"})
        original = builtin_catalog()
        summarizing = original.get("compaction")
        alternative = replace(summarizing, descriptor=replace(
            summarizing.descriptor, mechanism_id="alternative-reducer",
            label="Alternative reducer", default_enabled=False,
        ))
        catalog = original.extended((alternative,))
        selected = self.selection(catalog=catalog, allow_incomplete=True)
        controller = RunConfigurationController(selected, catalog)
        controller.select_algorithm("reduction", "alternative-reducer")
        group = next(item for item in controller.snapshot().selection_groups
                     if item.group_id == "reduction")
        self.assertEqual(set(group.option_ids), {"compaction", "alternative-reducer"})
        self.assertEqual(group.selected_id, "alternative-reducer")
        self.assertFalse(next(item for item in controller.snapshot().mechanisms
                              if item.mechanism_id == "compaction").enabled)

    def test_prompt_choice_is_staged_and_persisted_for_next_session(self) -> None:
        root = self.root
        _write_catalog(root / "models.yaml", {"local": "model-a"})
        catalog = builtin_catalog()
        selection = self.selection(catalog=catalog)
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
        root = self.root
        _write_catalog(root / "models.yaml", {"local": "model-a"})
        catalog = builtin_catalog()
        selected = self.selection(catalog=catalog)
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
        root = self.root
        model_path = root / "models.yaml"
        _write_catalog(model_path, {"local": "model-a"})

        selected = self.selection(catalog=builtin_catalog())

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
        root = self.root
        _write_catalog(root / "models.yaml", {"a": "model-a", "b": "model-b"})
        selected = self.selection(catalog=builtin_catalog(), allow_incomplete=True)

        self.assertIsNone(selected.profile.model_profile)

    def test_blank_initial_model_choice_is_unselected(self) -> None:
        for value in (None, "", " \t "):
            environment = {} if value is None else {"FRUITFLY_MODEL_PROFILE": value}
            with self.subTest(value=value):
                _write_catalog(self.root / "models.yaml", {"only": "model-a"})
                self.assertEqual(self.selection(environment=environment).profile.model_profile, "only")
                _write_catalog(self.root / "models.yaml", {"a": "model-a", "b": "model-b"})
                self.assertIsNone(self.selection(environment=environment, allow_incomplete=True).profile.model_profile)
                with self.assertRaisesRegex(ValueError, "ambiguous.*FRUITFLY_MODEL_PROFILE"):
                    self.selection(environment=environment)

    def test_explicit_initial_model_choice_is_validated_and_saved_choice_wins(self) -> None:
        _write_catalog(self.root / "models.yaml", {"a": "model-a", "b": "model-b"})
        chosen = self.selection(environment={"FRUITFLY_MODEL_PROFILE": "b"})
        self.assertEqual(chosen.profile.model_profile, "b")
        for incomplete in (False, True):
            with self.subTest(incomplete=incomplete), self.assertRaisesRegex(ValueError, "FRUITFLY_MODEL_PROFILE.*missing.*a, b"):
                self.selection(environment={"FRUITFLY_MODEL_PROFILE": "missing"}, allow_incomplete=incomplete)
        RunConfigurationController(chosen, builtin_catalog()).save()
        self.assertEqual(self.selection(environment={"FRUITFLY_MODEL_PROFILE": "missing"}).profile.model_profile, "b")

    def test_controller_saves_only_profile_state_for_a_future_session(self) -> None:
        root = self.root
        _write_catalog(root / "models.yaml", {"a": "model-a", "b": "model-b"})
        catalog = builtin_catalog()
        selected = self.selection(catalog=catalog, allow_incomplete=True)
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
        root = self.root
        _write_catalog(root / "models.yaml", {"only": "model-a"})
        catalog = builtin_catalog()
        selected = self.selection(catalog=catalog)
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
        root = self.root
        _write_catalog(root / "models.yaml", {"only": "model-a"})
        catalog = builtin_catalog()
        selected = self.selection(catalog=catalog)
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
        root = self.root
        catalog_dir = root / "configs"
        catalog_dir.mkdir()
        _write_catalog(catalog_dir / "models.yaml", {"only": "model-a"})
        catalog = builtin_catalog()
        selected = self.selection(catalog=catalog, allow_incomplete=True)
        controller = RunConfigurationController(selected, catalog)

        controller.select_model_catalog("../configs/models.yaml")
        snapshot = controller.snapshot()

        self.assertEqual(snapshot.model_catalog, "../configs/models.yaml")
        self.assertEqual(snapshot.model_profile, "only")
        self.assertEqual(snapshot.model_profiles, ("only",))

    def test_controller_exposes_and_enables_rlm_through_generic_configuration(
        self,
    ) -> None:
        root = self.root
        _write_catalog(root / "models.yaml", {"only": "model-a"})
        catalog = builtin_catalog()
        selected = self.selection(catalog=catalog)
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
        root = self.root
        _write_catalog(root / "models.yaml", {"only": "model-a"})
        catalog = builtin_catalog()
        selected = self.selection(catalog=catalog)
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
        root = self.root
        model_path = root / "models.yaml"
        _write_catalog(model_path, {"first": "model-a"})
        catalog = builtin_catalog()
        selected = self.selection(catalog=catalog)
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
