"""Builtin catalog behavior and failure contracts."""
from __future__ import annotations
import unittest
from pathlib import Path
from fruitfly_agent.lab.catalog import MechanismSelection, builtin_catalog


class CatalogTest(unittest.TestCase):
    def test_all_registered_algorithms_declare_differentiated_descriptions_and_real_paths(self):
        definitions = builtin_catalog().definitions()
        descriptions = [d.descriptor.description for d in definitions]
        self.assertEqual(len(descriptions), len(set(descriptions)))
        root = Path(__file__).resolve().parents[2]
        for definition in definitions:
            with self.subTest(method=definition.descriptor.mechanism_id):
                self.assertTrue((root / definition.implementation_path).is_file())
                self.assertTrue((root / definition.documentation_path).is_file())
        self.assertEqual(builtin_catalog().get('working-memory-reduction').input_parameters, ())
        self.assertEqual(builtin_catalog().get('live-http').input_parameters, ('endpoint',))

    def test_builtin_descriptors_use_two_dimensional_architecture(self) -> None:
        catalog = builtin_catalog()
        expected = {
            "read-tool": ("capability", "tools", None, "tools"),
            "ipython-tool": ("capability", "tools", None, "tools"),
            "skill-catalog": (
                "online",
                "context",
                "augmentation",
                "context-manager",
            ),
            "rlm-ipython": (
                "online",
                "context",
                "externalization",
                "context-manager",
            ),
            "working-memory-reduction": (
                "online",
                "context",
                "reduction",
                "context-manager",
            ),
        }
        for mechanism_id, coordinates in expected.items():
            descriptor = catalog.get(mechanism_id).descriptor
            primary = descriptor.primary
            self.assertEqual(
                coordinates[:3],
                (
                    primary.layer,
                    primary.family,
                    primary.context_phase,
                ),
            )

    def test_builtin_catalog_covers_every_current_selectable_harness_feature(self) -> None:
        self.assertEqual(
            {item.mechanism_id for item in builtin_catalog().descriptors()},
            {
                "local-env",
                "instruction-components",
                "ssh-env",
                "read-tool",
                "bash-tool",
                "edit-tool",
                "write-tool",
                "save-media-tool",
                "ipython-tool",
                "web-search-tool",
                "web-fetch-tool",
                "mcp-tools",
                "skill-catalog",
                "information-context",
                "memory-files",
                "knowledge-files",
                "live-http",
                "working-memory-reduction",
                "context-history",
                "rlm-ipython",
                "skill-document",
                "component-improvement",
            },
        )

    def test_current_configuration_rejects_retired_components(self):
        from fruitfly_agent.lab.catalog.configuration import configuration_surfaces
        catalog = builtin_catalog()
        for name in ('compaction', 'context-measurement', 'execution-workflow', 'learned-memory'):
            with self.subTest(component=name), self.assertRaises(ValueError): catalog.get(name)
        for name in ('improvement-feedback', 'improvement-search'):
            self.assertNotIn(name, configuration_surfaces(catalog))

    def test_ipython_and_rlm_descriptors_have_separate_effects(self) -> None:
        catalog = builtin_catalog()
        descriptor = catalog.get("rlm-ipython").descriptor
        tool = catalog.get("ipython-tool").descriptor

        self.assertEqual(
            ("online", "context", "externalization"),
            (
                descriptor.primary.layer,
                descriptor.primary.family,
                descriptor.primary.context_phase,
            ),
        )
        self.assertFalse(descriptor.default_enabled)
        self.assertEqual(frozenset({"ipython-tool"}), descriptor.requires)
        self.assertEqual((), descriptor.effects.tools)
        self.assertFalse(descriptor.effects.uses_provider)
        self.assertFalse(descriptor.effects.uses_network)
        self.assertTrue(descriptor.effects.writes_files)
        self.assertEqual(("ipython",), tool.effects.tools)
        self.assertTrue(tool.effects.uses_provider)
        self.assertTrue(tool.effects.uses_network)
        self.assertIn(
            "query_timeout_seconds",
            {parameter.name for parameter in tool.parameters},
        )

    def test_compaction_descriptor_owns_config_and_costs(self) -> None:
        definition = builtin_catalog().get("working-memory-reduction")
        descriptor = definition.descriptor
        self.assertEqual("reduction", descriptor.primary.context_phase)
        self.assertNotIn("profile", {p.name for p in descriptor.parameters})
        self.assertTrue(descriptor.effects.uses_provider)
        self.assertTrue(descriptor.effects.uses_network)
        self.assertEqual("working-memory-v1", definition.implementation_id)

    def test_compaction_rejects_profile_parameter_even_when_disabled(self):
        for name in ("unregistered-profile", "retired-method"):
            for enabled in (True, False):
                with self.subTest(name=name, enabled=enabled):
                    with self.assertRaisesRegex(ValueError, "unknown context policy parameter: profile"):
                        builtin_catalog().resolve((MechanismSelection(
                            "working-memory-reduction", enabled=enabled, parameters={"profile": name}
                        ),))
