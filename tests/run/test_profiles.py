from __future__ import annotations

import tempfile
import unittest
from pathlib import Path


from fruitfly_agent.lab.catalog import MechanismSelection, builtin_catalog
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
                "compaction",
            ),
        )

    def test_round_trip_schema_is_strict_and_hash_is_deterministic(self) -> None:
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
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fruitfly.yaml"
            save_harness_config(path, config)
            loaded = load_harness_config(path)

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
                load_harness_config(path)
