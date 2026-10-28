from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path


from fruitfly_agent.lab.catalog import (MechanismSelection, builtin_catalog, ParameterDescriptor,
    component_profile, configure_profile)
from fruitfly_agent.run.configuration import (
    HarnessConfig,
    HarnessProfile,
    load_harness_config,
    save_harness_config,
)


class HarnessProfileTest(unittest.TestCase):
    def test_hidden_harness_config_resolves_against_the_builtin_catalog(self) -> None:
        catalog = builtin_catalog()
        config = HarnessConfig(
            "default",
            {
                "default": HarnessProfile(
                    "default",
                    model_catalog="../models.yaml",
                    model_profile="offline",
                    mechanisms=catalog.default_selections(),
                )
            },
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".fruitfly" / "config.yaml"
            save_harness_config(path, config)
            loaded = load_harness_config(path)

        resolved = catalog.resolve(loaded.select().mechanisms)

        self.assertEqual(
            tuple(item.definition.descriptor.mechanism_id for item in resolved),
            (
                "local-env",
                "read-tool",
                "bash-tool",
                "edit-tool",
                "write-tool",
                "skill-catalog",
                "information-context",
                "memory-files",
                "context-history",
                "context-measurement",
                "compaction",
                "component-improvement",
            ),
        )

    def test_round_trip_schema_is_strict_and_hash_is_deterministic(self) -> None:
        base = builtin_catalog()
        template = base.get('local-env')
        custom = replace(template, descriptor=replace(template.descriptor, mechanism_id='custom',
            parameters=(ParameterDescriptor('limit', 'integer', 'Limit', 'Offline fixture limit.', 1),)))
        catalog = base.extended((custom,))
        config = HarnessConfig(
            "default",
            {
                "default": HarnessProfile(
                    "default",
                    model_profile="offline",
                    mechanisms=(
                        MechanismSelection("custom", parameters={"limit": 3}),
                    ),
                )
            },
        )
        config = replace(config, profiles={key: configure_profile(component_profile(value, catalog), catalog)
                                          for key, value in config.profiles.items()})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fruitfly.yaml"
            save_harness_config(path, config, catalog=catalog)
            loaded = load_harness_config(path, catalog=catalog)

            self.assertEqual(loaded, config)
            self.assertEqual(
                loaded.select().profile_hash,
                config.select().profile_hash,
            )
            path.write_text(
                path.read_text(encoding="utf-8") + "unknown: true\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "unknown harness config"):
                load_harness_config(path, catalog=catalog)
