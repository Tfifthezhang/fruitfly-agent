"""Model persistence behavior and failure contracts."""
import tempfile
import unittest
from unittest.mock import patch
from fruitfly_agent.providers.registry import load_model_specs
from tests.support.run import _write_catalog

from tests.support.model_setup import ModelSetupWorkspace


class ModelSetupTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.workspace = ModelSetupWorkspace(self.enterContext(tempfile.TemporaryDirectory()))

    def test_catalog_and_environment_content_are_preserved(self):
        catalog = self.workspace.root / ".fruitfly/models.yaml"
        _write_catalog(catalog, {"existing": "old-model"})
        original = "# Keep this comment\n" + catalog.read_text() + "# Tail comment\nmetadata:\n  other: preserved\n"
        catalog.write_text(original)
        (self.workspace.root / ".fruitfly/secrets.env").write_text("# Keep credentials\nUNRELATED=value\nEMPTY=\n")
        self.workspace.stage()
        self.assertFalse((self.workspace.root / ".fruitfly/secrets.env").read_text().endswith("offline-placeholder\n"))
        self.workspace.controller.save()
        text = catalog.read_text()
        self.assertIn("# Keep this comment", text)
        self.assertIn("# Tail comment\n", text)
        self.assertIn("other: preserved\n", text)
        self.assertEqual(load_model_specs(catalog)["existing"].model, "old-model")
        self.assertTrue((self.workspace.root / ".fruitfly/secrets.env").read_text().startswith("# Keep credentials\nUNRELATED=value\nEMPTY=\n"))

    def test_existing_environment_key_is_reused_without_writing_env(self):
        self.workspace.factory.environment["EXISTING_KEY"] = "offline-placeholder"
        self.workspace.setup.stage("anthropic", {**self.workspace.values, "api_key_env": "EXISTING_KEY"}, "")
        self.workspace.controller.save()
        self.assertFalse((self.workspace.root / ".fruitfly/secrets.env").exists())
        self.assertEqual(load_model_specs(self.workspace.root / ".fruitfly/models.yaml")["local"].provider.sdk, "anthropic")

    def test_missing_key_and_existing_key_conflict_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "missing"):
            self.workspace.setup.stage("openai", self.workspace.values, "")
        self.workspace.factory.environment["EXISTING_KEY"] = "first-placeholder"
        with self.assertRaisesRegex(ValueError, "already set"):
            self.workspace.stage(api_key_env="EXISTING_KEY")
        self.assertFalse(self.workspace.setup.changed)

    def test_save_failure_restores_files_and_retains_draft_for_retry(self):
        (self.workspace.root / ".fruitfly/secrets.env").write_text("# original\nOTHER=value\n")
        self.workspace.stage()
        with patch("fruitfly_agent.run.configuration.controller.save_harness_config", side_effect=OSError("offline write failure")):
            with self.assertRaises(OSError):
                self.workspace.controller.save()
        self.assertFalse((self.workspace.root / ".fruitfly/models.yaml").exists())
        self.assertEqual((self.workspace.root / ".fruitfly/secrets.env").read_text(), "# original\nOTHER=value\n")
        self.assertNotIn("FRUITFLY_MODEL_LOCAL_API_KEY", self.workspace.factory.environment)
        self.assertTrue(self.workspace.controller.snapshot().changed)
        self.workspace.controller.save()
        self.assertFalse(self.workspace.controller.snapshot().changed)

    def test_concurrent_duplicate_and_secret_symlink_are_rejected(self):
        self.workspace.stage()
        _write_catalog(self.workspace.root / ".fruitfly/models.yaml", {"local": "other-model"})
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.workspace.controller.save()
        self.assertEqual(load_model_specs(self.workspace.root / ".fruitfly/models.yaml")["local"].model, "other-model")
        (self.workspace.root / ".fruitfly/models.yaml").unlink()
        target = self.workspace.root / "external-env"
        target.write_text("OTHER=value\n")
        (self.workspace.root / ".fruitfly/secrets.env").symlink_to(target)
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.workspace.controller.save()
        self.assertEqual(target.read_text(), "OTHER=value\n")

    def test_credential_repair_is_staged_and_discardable(self):
        self.workspace.stage()
        self.workspace.controller.save()
        self.workspace.factory.environment.clear()
        (self.workspace.root / ".fruitfly/secrets.env").unlink()
        self.assertEqual(self.workspace.setup.credential_status("local"), "API key missing")
        self.workspace.setup.stage_credential("local", "second-placeholder")
        self.assertTrue(self.workspace.controller.snapshot().changed)
        self.workspace.controller.reset()
        self.assertEqual(self.workspace.setup.credential_status("local"), "API key missing")
        self.assertFalse((self.workspace.root / ".fruitfly/secrets.env").exists())

    def test_changed_credential_file_is_preserved_on_save(self):
        self.workspace.stage()
        (self.workspace.root / ".fruitfly/secrets.env").write_text("FRUITFLY_MODEL_LOCAL_API_KEY=other-placeholder\n")
        with self.assertRaisesRegex(ValueError, "different value"):
            self.workspace.controller.save()
        self.assertFalse((self.workspace.root / ".fruitfly/models.yaml").exists())
        self.assertEqual((self.workspace.root / ".fruitfly/secrets.env").read_text(), "FRUITFLY_MODEL_LOCAL_API_KEY=other-placeholder\n")

    def test_failed_save_restores_original_catalog_before_field_reordering(self):
        catalog = self.workspace.root / '.fruitfly/models.yaml'
        _write_catalog(catalog, {'existing': 'old-model'})
        original = catalog.read_bytes()
        self.workspace.stage()
        with patch('fruitfly_agent.run.configuration.controller.save_harness_config', side_effect=OSError('offline write failure')):
            with self.assertRaises(OSError):
                self.workspace.controller.save()
        self.assertEqual(catalog.read_bytes(), original)
        self.assertTrue(self.workspace.setup.changed)
