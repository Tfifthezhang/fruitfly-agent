"""Workspace precedence and explicit configuration relocation, entirely offline."""

import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from fruitfly_agent.interactive import ConfigurationLaunchResult
from fruitfly_agent.providers.config import load_env
from fruitfly_agent.providers.workspace import WorkspacePaths
from fruitfly_agent.run.application import RunApplicationFactory
from fruitfly_agent.run import cli
from fruitfly_agent.run.configuration import HarnessConfig, HarnessProfile, load_harness_config, save_harness_config
from fruitfly_agent.run.migrate_configuration import migrate_configuration
from tests.support.faux_provider import FauxProvider
from tests.support.run import _args, _write_catalog


class ConfigurationPathsTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.paths = WorkspacePaths(self.root)
        self.paths.models.parent.mkdir()
        self.config = self.root / ".fruitfly/config.yaml"

    def legacy(self):
        _write_catalog(self.paths.legacy_models, {"offline": "offline-model"})
        self.paths.legacy_secrets.write_text("# retained\nFAKE_KEY=offline-placeholder\nOTHER=value\n")
        save_harness_config(self.config, HarnessConfig("first", {
            "first": HarnessProfile("first", "../models.yaml", "offline"),
            "second": HarnessProfile("second", str(self.paths.legacy_models), "offline"),
            "external": HarnessProfile("external", "other-models.yaml", "other"),
        }))

    async def test_cli_prefers_new_secrets_without_merging_and_reports_both_files(self):
        self.legacy()
        _write_catalog(self.paths.models, {"new": "new-model"})
        self.paths.secrets.write_text("FAKE_KEY=new-placeholder\nNEW_ONLY=value\n")
        frontend = Mock()
        frontend.run.return_value = ConfigurationLaunchResult(start=False)
        errors = io.StringIO()
        with patch.dict(os.environ, {"FAKE_KEY": ""}, clear=True), patch.object(
            cli, "RunApplicationFactory"
        ) as factory, patch.object(cli, "TerminalConfigurationFrontend", return_value=frontend), contextlib.redirect_stderr(errors):
            self.assertEqual(await cli.run_cli(_args(cwd=str(self.root))), 0)
        env = factory.call_args.kwargs["environment"]
        self.assertEqual(env["FAKE_KEY"], "")
        self.assertEqual(env["NEW_ONLY"], "value")
        self.assertNotIn("OTHER", env)
        self.assertIn("saved catalog paths take precedence", errors.getvalue())
        self.assertIn("not merged", errors.getvalue())
        self.assertNotIn("new-placeholder", errors.getvalue())
        # Persisted paths win even when new discovery files exist.
        actual = RunApplicationFactory(cwd=self.root, environment={})
        self.assertEqual(actual.selection.profile.model_catalog, "../models.yaml")
        self.config.unlink()
        actual = RunApplicationFactory(cwd=self.root, environment={})
        self.assertEqual(actual.selection.profile.model_profile, "new")

    def test_legacy_read_and_wizard_save_keep_explicit_legacy_files(self):
        self.legacy()
        # Remove the unused external profile to permit ordinary save validation.
        config = load_harness_config(self.config)
        save_harness_config(self.config, HarnessConfig("first", {"first": config.profiles["first"]}))
        factory = RunApplicationFactory(cwd=self.root, environment=load_env(self.paths.secret_file()))
        factory.configuration.model_setup.stage("openai", dict(profile="added", model="offline",
            context_window="8192", max_output_tokens="1024", base_url="", api_key_env=""), "added-placeholder")
        factory.configuration.save()
        self.assertFalse(self.paths.models.exists())
        self.assertFalse(self.paths.secrets.exists())
        self.assertIn("FRUITFLY_MODEL_ADDED_API_KEY", load_env(self.paths.legacy_secrets))

    def test_preview_writes_nothing_and_apply_preserves_text_and_all_matching_profiles(self):
        self.legacy()
        self.config.write_text("# harness comment\n" + self.config.read_text())
        original = {path: path.read_bytes() for path in (self.paths.legacy_models, self.paths.legacy_secrets, self.config)}
        preview = migrate_configuration(self.root)
        self.assertIn("Preview only", preview[-1])
        for path, data in original.items():
            self.assertEqual(path.read_bytes(), data)
        self.assertFalse(self.paths.models.exists())
        migrate_configuration(self.root, apply=True)
        self.assertEqual(self.paths.models.read_bytes(), original[self.paths.legacy_models])
        self.assertEqual(self.paths.secrets.read_bytes(), original[self.paths.legacy_secrets])
        self.assertEqual(self.paths.secrets.stat().st_mode & 0o777, 0o600)
        config = load_harness_config(self.config)
        self.assertEqual(config.profiles["first"].model_catalog, "models.yaml")
        self.assertEqual(config.profiles["second"].model_catalog, "models.yaml")
        self.assertEqual(config.profiles["external"].model_catalog, "other-models.yaml")
        self.assertTrue(self.config.read_text().startswith("# harness comment\n"))
        self.assertFalse(self.paths.legacy_models.exists())
        self.assertFalse(self.paths.legacy_secrets.exists())
        self.assertIn("No legacy", migrate_configuration(self.root, apply=True)[0])

    def test_destination_conflict_and_symlink_fail_without_changes(self):
        self.legacy()
        for target in (self.paths.models, self.paths.secrets):
            target.write_text("do not replace")
            with self.assertRaisesRegex(ValueError, "already exists"):
                migrate_configuration(self.root, apply=True)
            self.assertEqual(target.read_text(), "do not replace")
            target.unlink()
        self.paths.secrets.symlink_to(self.paths.legacy_secrets)
        with self.assertRaises(ValueError):
            migrate_configuration(self.root, apply=True)
        self.assertTrue(self.paths.legacy_models.is_file())

    def test_failure_restores_configuration_and_legacy_files(self):
        self.legacy()
        before = self.config.read_bytes()
        unlink = Path.unlink
        def fail_secret_removal(path, *args, **kwargs):
            if path == self.paths.legacy_secrets:
                raise OSError("offline deletion failure")
            return unlink(path, *args, **kwargs)
        with patch.object(Path, "unlink", fail_secret_removal):
            # Exercise rollback after destinations and configuration were written.
            with self.assertRaises(OSError):
                migrate_configuration(self.root, apply=True)
        self.assertEqual(self.config.read_bytes(), before)
        self.assertTrue(self.paths.legacy_models.exists())
        self.assertTrue(self.paths.legacy_secrets.exists())
        self.assertFalse(self.paths.models.exists())
        self.assertFalse(self.paths.secrets.exists())

    def test_implicit_catalog_paths_in_custom_config_are_updated(self):
        self.legacy()
        custom = self.root / "custom.yaml"
        for model in ('{profile: offline}', '  profile: offline\n'):
            custom.write_text("schema_version: 1\ndefault_profile: first\nprofiles:\n  first:\n    model: " + model + "\n")
            # Block YAML needs the model entry on its own line.
            if not model.startswith('{'):
                custom.write_text("schema_version: 1\ndefault_profile: first\nprofiles:\n  first:\n    model:\n      profile: offline\n")
            migrate_configuration(self.root, config_path=custom, apply=True)
            self.assertEqual(load_harness_config(custom).select().model_catalog, ".fruitfly/models.yaml")
            self.paths.models.rename(self.paths.legacy_models)
            self.paths.secrets.rename(self.paths.legacy_secrets)

    async def test_moved_catalog_resumes_existing_manifest_and_artifacts(self):
        self.legacy()
        registry = Mock()
        provider = FauxProvider()
        provider.respond_text("saved")
        registry.create.return_value = provider
        factory = RunApplicationFactory(cwd=self.root, environment={}, provider_registry=registry)
        session_path = self.root / ".fruitfly/sessions/offline.jsonl"
        handle = await factory.open(resume=False, session_path=session_path)
        manifest = handle.manifest
        await handle.session.submit("offline task")
        await handle.close()
        migrate_configuration(self.root, apply=True)
        restored = RunApplicationFactory(cwd=self.root, environment={}, provider_registry=registry)
        handle = await restored.open(resume=True, session_path=session_path)
        try:
            self.assertEqual(handle.manifest, manifest)
        finally:
            await handle.close()
