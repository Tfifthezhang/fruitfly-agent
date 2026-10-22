"""Guided remote setup, hidden credentials and shared save transaction."""
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fruitfly_agent.interactive import TerminalConfigurationFrontend
from fruitfly_agent.interactive.terminal.features.configuration.mechanism_setup import run_mechanism_setup
from fruitfly_agent.providers.config import load_env
from fruitfly_agent.run import RunApplicationFactory
from tests.support.run import _write_catalog
from tests.support.terminal import MenuScriptedLines


class MechanismSetupTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        _write_catalog(self.root / 'models.yaml', {'offline': 'offline-model'})
        self.factory = RunApplicationFactory(cwd=self.root, environment={'TEST_API_KEY': 'fixture-model-key'})
        self.configuration = self.factory.configuration
        self.service = self.configuration.mechanism_setup
        self.output = io.StringIO()
        self.initial_changed = self.configuration.changed

    def frontend(self, *lines, secrets='fixture-private-account\nfixture-private-password\n'):
        return TerminalConfigurationFrontend(self.configuration, input_stream=io.StringIO(secrets),
            output_stream=self.output, line_editor=MenuScriptedLines(self.output, *lines))

    def stage(self, **secrets):
        return self.service.stage('ssh-env', {'host': 'server.example', 'port': '2222',
            'cwd': '/srv/project', 'known_hosts': '~/.ssh/known_hosts'},
            {'username_env': 'fixture-private-account', 'password_env': 'fixture-private-password', **secrets})

    def assert_hidden(self):
        for value in ('fixture-private-account', 'fixture-private-password'):
            self.assertNotIn(value, self.output.getvalue())
            self.assertNotIn(value, repr(self.configuration.snapshot()))
            path = self.root / '.fruitfly/config.yaml'
            if path.exists():
                self.assertNotIn(value, path.read_text())

    def test_enabling_remote_opens_wizard_and_saves_hidden_credentials_with_configuration(self):
        frontend = self.frontend('@Configure', '@Environment', '@Remote environment', 'space',
            'server.example', '2222', '/srv/project', '', '@Stage settings', 'back', 'back', 'back', '@Start new session')
        result = frontend.run()
        self.assertTrue(result.start)
        self.assertTrue(result.saved)
        text = self.output.getvalue()
        self.assertIn('Set up Remote environment · Step 1 of 6', text)
        self.assertIn('Step 6 of 6', text)
        self.assertIn('fingerprint', text)
        self.assertIn('Account: entered (value hidden)', text)
        self.assertIn('Password: entered (value hidden)', text)
        self.assertNotIn('SSH requires', text)
        path = self.root / '.fruitfly/secrets.env'
        self.assertEqual('fixture-private-account', load_env(path)['FRUITFLY_SSH_USERNAME'])
        self.assertEqual('fixture-private-password', load_env(path)['FRUITFLY_SSH_PASSWORD'])
        self.assertEqual(0o600, path.stat().st_mode & 0o777)
        self.assertEqual('fixture-private-password', self.factory.environment['FRUITFLY_SSH_PASSWORD'])
        enabled = {m.mechanism_id for m in self.configuration.profile().mechanisms if m.enabled}
        self.assertIn('ssh-env', enabled)
        self.assertNotIn('local-env', enabled)
        self.assert_hidden()

    def test_starting_existing_remote_configuration_with_missing_secrets_guides_repair(self):
        self.factory.environment.update(FRUITFLY_SSH_USERNAME='fixture-private-account',
                                        FRUITFLY_SSH_PASSWORD='fixture-private-password')
        self.configuration.set_mechanism('ssh-env', enabled=True)
        self.configuration.set_parameter('ssh-env', 'host', 'server.example')
        self.configuration.save()
        self.factory.environment.pop('FRUITFLY_SSH_USERNAME')
        self.factory.environment.pop('FRUITFLY_SSH_PASSWORD')
        snapshot = self.configuration.snapshot()
        self.assertFalse(snapshot.ready)
        self.assertIn('Set up…', ' '.join(snapshot.warnings))
        frontend = self.frontend('@Start new session', '', '', '', '', '@Stage settings')
        with patch('fruitfly_agent.lab.environment.ssh.SshEnv.start', side_effect=AssertionError('setup made a connection')):
            result = frontend.run()
        self.assertTrue(result.start)
        self.assertTrue(result.saved)
        self.assertTrue(self.configuration.snapshot().ready)
        self.assert_hidden()

    def test_cancel_at_field_secret_review_or_discard_keeps_original_environment(self):
        scenarios = (
            (('@Configure', '@Environment', '@Remote environment', 'space', '/cancel', 'back', 'back', 'back', '@Exit'), ''),
            (('@Configure', '@Environment', '@Remote environment', 'space', 'server.example', '', '', '',
              'back', 'back', 'back', '@Exit'), '/cancel\n'),
            (('@Configure', '@Environment', '@Remote environment', 'space', 'server.example', '', '', '',
              '@Cancel', 'back', 'back', 'back', '@Exit'), 'fixture-private-account\nfixture-private-password\n'),
            (('@Configure', '@Environment', '@Remote environment', 'space', 'server.example', '', '', '',
              '@Stage settings', 'back', 'back', 'back', '@Exit'), 'fixture-private-account\nfixture-private-password\n'),
        )
        for lines, secrets in scenarios:
            with self.subTest(lines=lines):
                self.output = io.StringIO()
                self.assertFalse(self.frontend(*lines, secrets=secrets).run().start)
                self.assertEqual(self.initial_changed, self.configuration.changed)
                self.assertTrue(next(m for m in self.configuration.profile().mechanisms if m.mechanism_id == 'local-env').enabled)
                self.assertFalse((self.root / '.fruitfly/secrets.env').exists())
                self.assertFalse((self.root / '.fruitfly/config.yaml').exists())
                self.assertNotIn('FRUITFLY_SSH_PASSWORD', self.factory.environment)
                self.assert_hidden()

    def test_invalid_fields_and_missing_secrets_retry_without_echo_or_partial_stage(self):
        frontend = self.frontend('server.example', '0', '2222', '/srv/project', '', '@Stage settings',
            secrets='\nfixture-private-account\n\nfixture-private-password\n')
        self.assertTrue(run_mechanism_setup(frontend._model_form(), self.service, 'ssh-env'))
        self.assertIn('Invalid SSH port', self.output.getvalue())
        self.assertIn('Account is missing', self.output.getvalue())
        self.assertIn('Password is missing', self.output.getvalue())
        self.assertTrue(self.configuration.changed)
        self.assertFalse((self.root / '.fruitfly/secrets.env').exists())
        self.assert_hidden()

    def test_blank_reuses_existing_secrets_and_explicit_setup_remains_available(self):
        self.stage()
        self.configuration.save()
        original = (self.root / '.fruitfly/secrets.env').read_bytes()
        self.output = io.StringIO()
        frontend = self.frontend('@Configure', '@Environment', '@Remote environment', '@Set up…',
            '', '', '', '', '@Stage settings', 'back', 'back', 'back', '@Start new session', secrets='\n\n')
        self.assertTrue(frontend.run().start)
        self.assertEqual(original, (self.root / '.fruitfly/secrets.env').read_bytes())
        self.assertIn('Account: reused', self.output.getvalue())
        self.assert_hidden()

    def test_rechecking_complete_staged_settings_skips_wizard(self):
        self.stage()
        parameters = next(m.parameters for m in self.configuration.profile().mechanisms if m.mechanism_id == 'ssh-env')
        frontend = self.frontend('@Configure', '@Environment', '@Remote environment', 'space', 'space',
            'back', 'back', 'back', '@Start new session', secrets='')
        with patch('fruitfly_agent.interactive.terminal.features.configuration.menu.run_mechanism_setup',
                   side_effect=AssertionError('complete settings reopened setup')):
            self.assertTrue(frontend.run().saved)
        remote = next(m for m in self.configuration.profile().mechanisms if m.mechanism_id == 'ssh-env')
        self.assertTrue(remote.enabled)
        self.assertEqual(parameters, remote.parameters)
        self.assert_hidden()

    def test_saved_remote_settings_survive_switch_to_local_and_new_process_selection(self):
        self.stage()
        self.configuration.save()
        secret_path = self.root / '.fruitfly/secrets.env'
        saved_secrets = secret_path.read_bytes()
        self.configuration.set_mechanism('local-env', enabled=True)
        self.configuration.save()
        # Recreate the host with only persisted credentials, as CLI startup does.
        self.factory = RunApplicationFactory(cwd=self.root,
            environment={**load_env(secret_path), 'TEST_API_KEY': 'fixture-model-key'})
        self.configuration = self.factory.configuration
        self.service = self.configuration.mechanism_setup
        self.output = io.StringIO()
        frontend = self.frontend('@Configure', '@Environment', '@Remote environment', 'space',
            'back', 'back', 'back', '@Start new session', secrets='')
        with patch('fruitfly_agent.interactive.terminal.features.configuration.menu.run_mechanism_setup',
                   side_effect=AssertionError('saved settings reopened setup')):
            self.assertTrue(frontend.run().saved)
        remote = next(m for m in self.configuration.profile().mechanisms if m.mechanism_id == 'ssh-env')
        self.assertTrue(remote.enabled)
        self.assertEqual('server.example', remote.parameters['host'])
        self.assertEqual(2222, remote.parameters['port'])
        self.assertEqual('/srv/project', remote.parameters['cwd'])
        self.assertEqual(saved_secrets, secret_path.read_bytes())
        self.assertNotIn('Set up Remote environment · Step', self.output.getvalue())
        self.assert_hidden()

    def test_rechecking_with_a_missing_credential_still_opens_setup(self):
        self.stage()
        self.configuration.save()
        self.configuration.set_mechanism('local-env', enabled=True)
        self.factory.environment.pop('FRUITFLY_SSH_PASSWORD')
        frontend = self.frontend('@Configure', '@Environment', '@Remote environment', 'space',
            '', '', '', '', '@Stage settings', 'back', 'back', 'back', '@Start new session',
            secrets='\nfixture-private-password\n')
        self.assertTrue(frontend.run().saved)
        self.assertIn('Set up Remote environment · Step', self.output.getvalue())
        self.assert_hidden()

    def test_shared_model_and_remote_credentials_are_saved_together_with_unrelated_content(self):
        secret_path = self.root / '.fruitfly/secrets.env'
        secret_path.parent.mkdir(exist_ok=True)
        secret_path.write_text('# Preserve me\nUNRELATED=value\n')
        self.configuration.model_setup.stage_credential('offline', '')
        self.configuration.model_setup.stage('openai', dict(profile='new', model='fixture', base_url='',
            context_window='8192', max_output_tokens='1024', api_key_env='NEW_KEY'), 'fixture-new-model-key')
        self.stage()
        self.configuration.save()
        self.assertTrue(secret_path.read_text().startswith('# Preserve me\nUNRELATED=value\n'))
        self.assertEqual({'UNRELATED', 'NEW_KEY', 'FRUITFLY_SSH_USERNAME', 'FRUITFLY_SSH_PASSWORD'}, set(load_env(secret_path)))
        self.assert_hidden()

    def test_failed_save_rolls_back_and_keeps_credentials_staged_for_retry(self):
        self.stage()
        with patch('fruitfly_agent.run.configuration.controller.save_harness_config', side_effect=OSError('fixture save failure')):
            with self.assertRaises(OSError):
                self.configuration.save()
        self.assertFalse((self.root / '.fruitfly/secrets.env').exists())
        self.assertNotIn('FRUITFLY_SSH_PASSWORD', self.factory.environment)
        self.assertTrue(self.configuration.changed)
        self.configuration.save()
        self.assertEqual('fixture-private-password', load_env(self.root / '.fruitfly/secrets.env')['FRUITFLY_SSH_PASSWORD'])

    def test_invalid_secret_never_stages_settings_and_symlink_destination_is_rejected(self):
        original = self.configuration.profile()
        for value in ('bad\nsecret', ' leading', 'trailing '):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.stage(password_env=value)
            self.assertEqual(original, self.configuration.profile())
            self.assertEqual(self.initial_changed, self.configuration.changed)
        self.stage()
        target = self.root / 'untouched'
        target.write_text('UNRELATED=value\n')
        path = self.root / '.fruitfly/secrets.env'
        path.parent.mkdir(exist_ok=True)
        path.symlink_to(target)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.configuration.save()
        self.assertEqual('UNRELATED=value\n', target.read_text())

    def test_incomplete_configuration_cannot_be_saved(self):
        self.configuration.set_mechanism('ssh-env', enabled=True)
        with self.assertRaisesRegex(ValueError, 'Set up…'):
            self.configuration.save()
        self.assertFalse((self.root / '.fruitfly/config.yaml').exists())
