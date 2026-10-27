"""Canonical discovery and explicit custom catalogs remain separate, offline."""
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
from fruitfly_agent.run.configuration import HarnessConfig, HarnessProfile, save_harness_config
from tests.support.run import _args, _write_catalog


class ConfigurationPathsTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.paths = WorkspacePaths(self.root)
        self.paths.models.parent.mkdir()

    async def test_cli_reads_only_canonical_secrets_and_process_values_win(self):
        (self.root / '.env').write_text('OLD_ONLY=fixture\nFAKE_KEY=old-fixture\n')
        self.paths.secrets.write_text('FAKE_KEY=current-fixture\nNEW_ONLY=value\n')
        frontend = Mock()
        frontend.run.return_value = ConfigurationLaunchResult(start=False)
        errors = io.StringIO()
        with patch.dict(os.environ, {'FAKE_KEY': ''}, clear=True), patch.object(
            cli, 'RunApplicationFactory'
        ) as factory, patch.object(cli, 'TerminalConfigurationFrontend', return_value=frontend), contextlib.redirect_stderr(errors):
            self.assertEqual(await cli.run_cli(_args(cwd=str(self.root))), 0)
        env = factory.call_args.kwargs['environment']
        self.assertEqual(env['FAKE_KEY'], '')
        self.assertEqual(env['NEW_ONLY'], 'value')
        self.assertNotIn('OLD_ONLY', env)
        self.assertEqual(errors.getvalue(), '')

    def test_discovery_does_not_fall_back_to_root_models_or_dotenv(self):
        _write_catalog(self.root / 'models.yaml', {'old': 'unused-model'})
        (self.root / '.env').write_text('OLD_ONLY=unused-fixture\n')
        self.assertIsNone(self.paths.model_catalog())
        self.assertEqual(load_env(self.paths.secret_file()), {})
        factory = RunApplicationFactory(cwd=self.root, environment={}, allow_incomplete=True)
        self.assertIsNone(factory.selection.profile.model_profile)
        _write_catalog(self.paths.models, {'current': 'current-model'})
        factory = RunApplicationFactory(cwd=self.root, environment={})
        self.assertEqual(factory.selection.profile.model_profile, 'current')

    def test_explicit_custom_catalog_is_supported_without_implicit_discovery(self):
        custom = self.root / 'custom-models.yaml'
        _write_catalog(custom, {'explicit': 'explicit-model'})
        save_harness_config(self.root / '.fruitfly/config.yaml', HarnessConfig('work', {
            'work': HarnessProfile('work', '../custom-models.yaml', 'explicit')}))
        _write_catalog(self.paths.models, {'default': 'default-model'})
        factory = RunApplicationFactory(cwd=self.root, environment={})
        self.assertEqual(factory.selection.profile.model_profile, 'explicit')
        self.assertEqual(factory.selection.profile.model_catalog, '../custom-models.yaml')

    def test_wizard_writes_canonical_secrets_and_keeps_unrelated_root_files(self):
        _write_catalog(self.paths.models, {'offline': 'offline-model'})
        root_secret = self.root / '.env'
        root_secret.write_text('UNRELATED=leave-this-file\n')
        factory = RunApplicationFactory(cwd=self.root, environment={})
        factory.configuration.model_setup.stage('openai', dict(profile='added', model='offline',
            context_window='8192', max_output_tokens='1024', base_url='', api_key_env=''), 'offline-placeholder')
        factory.configuration.save()
        self.assertIn('FRUITFLY_MODEL_ADDED_API_KEY', load_env(self.paths.secrets))
        self.assertEqual(root_secret.read_text(), 'UNRELATED=leave-this-file\n')
        self.assertEqual(self.paths.secrets.stat().st_mode & 0o777, 0o600)
