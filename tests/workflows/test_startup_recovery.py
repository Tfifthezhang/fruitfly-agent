"""Offline CLI recovery from unavailable execution environments."""
import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from fruitfly_agent.interactive import TerminalConfigurationFrontend
from fruitfly_agent.lab.environment.ssh import SshEnv
from fruitfly_agent.run import cli
from fruitfly_agent.run.application import RunApplicationFactory
from fruitfly_agent.run.configuration import load_harness_config
from tests.support.faux_provider import FauxProvider
from tests.support.run import _args, _write_catalog, _seed_resumable_session
from fruitfly_agent.core.session import Session
from tests.support.terminal import MenuScriptedLines


class StartupRecoveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        _write_catalog(self.root / '.fruitfly/models.yaml', {'offline': 'offline-model'})
        self.provider = FauxProvider()
        self.registry = Mock()
        self.registry.create.return_value = self.provider
        self.environment = {'TEST_API_KEY': 'fixture-model-secret',
            'FRUITFLY_SSH_USERNAME': 'fixture-private-account',
            'FRUITFLY_SSH_PASSWORD': 'fixture-private-password'}
        self.factory = RunApplicationFactory(cwd=self.root, environment=self.environment,
            provider_registry=self.registry, allow_incomplete=True)
        controller = self.factory.configuration
        controller.set_mechanism('working-memory-reduction', enabled=False)
        controller.set_mechanism('ssh-env', enabled=True)
        controller.set_parameter('ssh-env', 'host', 'unavailable.example')
        controller.save()
        self.factory.reload_configuration()

    async def test_unreachable_remote_can_be_changed_in_shared_editor_then_started_locally(self):
        output = io.StringIO()
        close = SshEnv.close
        closes = []
        async def record_close(backend):
            closes.append(backend)
            await close(backend)
        def editor(configuration):
            return TerminalConfigurationFrontend(configuration, output_stream=output,
                line_editor=MenuScriptedLines(output, '@Environment', '@Local environment', 'space',
                    'back', 'back', '@Save and return'))
        with patch.object(cli, 'RunApplicationFactory', return_value=self.factory), patch.object(
                cli, 'TerminalConfigurationFrontend', side_effect=editor), patch.object(
                SshEnv, '_connect', side_effect=OSError('fixture network unavailable')) as connection, patch.object(
                SshEnv, 'close', record_close), patch('sys.stdin', io.StringIO('1\n2\n1\n/exit\n')), \
                contextlib.redirect_stdout(output):
            self.assertEqual(await cli.run_cli(_args(cwd=str(self.root))), 0)
        self.assertEqual(connection.call_count, 1)
        self.assertTrue(closes)
        self.assertIn('Startup failed: SSH connection failed', output.getvalue())
        self.assertIn('Configuration saved', output.getvalue())
        self.assertIn('Environment: Local', output.getvalue())
        self.assertIn('FruitFlyAgent interactive', output.getvalue())
        saved = load_harness_config(self.root / '.fruitfly/config.yaml').select()
        self.assertIn('local-env', {m.mechanism_id for m in saved.mechanisms if m.enabled})
        self.assertEqual(self.provider.calls, [])
        for value in self.environment.values():
            self.assertNotIn(value, output.getvalue())

    async def test_opening_and_exiting_remote_panel_does_not_connect_or_create_session(self):
        before = (self.root / '.fruitfly/config.yaml').read_bytes()
        with patch.object(cli, 'RunApplicationFactory', return_value=self.factory), patch.object(
                SshEnv, '_connect', side_effect=AssertionError('panel connected')) as connection, patch.object(
                cli, 'AgentApplication') as application, patch('sys.stdin', io.StringIO('q\n')), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(await cli.run_cli(_args(cwd=str(self.root))), 0)
        connection.assert_not_called()
        application.assert_not_called()
        self.registry.create.assert_not_called()
        self.assertFalse((self.root / '.fruitfly/sessions').exists())
        self.assertEqual((self.root / '.fruitfly/config.yaml').read_bytes(), before)

    async def test_resume_failure_returns_to_panel_without_modifying_history(self):
        path = self.root / 'corrupt-session.jsonl'
        _seed_resumable_session(path)
        with Session(path) as session:
            session.append('meta', {'kind': 'runtimeManifest', 'manifest': {'schema_version': 0}})
        before = path.read_bytes()
        output = io.StringIO()
        with patch.object(cli, 'RunApplicationFactory', return_value=self.factory), patch.object(
                SshEnv, '_connect', side_effect=AssertionError('invalid history connected')) as connection, \
                patch('sys.stdin', io.StringIO('1\nq\n')), contextlib.redirect_stdout(output):
            self.assertEqual(await cli.run_cli(_args(cwd=str(self.root), resume=True, session=str(path))), 0)
        connection.assert_not_called()
        self.assertIn('Startup failed', output.getvalue())
        self.assertEqual(path.read_bytes(), before)

    async def test_configure_saves_remote_settings_and_returns_without_connecting(self):
        self.factory.configuration.set_parameter('ssh-env', 'host', 'changed.example')
        output = io.StringIO()
        def editor(configuration):
            return TerminalConfigurationFrontend(configuration, output_stream=output,
                line_editor=MenuScriptedLines(output, 'back', '@Save and return'))
        with patch.object(cli, 'RunApplicationFactory', return_value=self.factory), patch.object(
                cli, 'TerminalConfigurationFrontend', side_effect=editor), patch.object(
                SshEnv, '_connect', side_effect=AssertionError('saving connected')) as connection, patch.object(
                cli, 'AgentApplication') as application, patch('sys.stdin', io.StringIO('q\n')), \
                contextlib.redirect_stdout(output):
            self.assertEqual(await cli.run_cli(_args(cwd=str(self.root), configure=True)), 0)
        connection.assert_not_called()
        application.assert_not_called()
        self.registry.create.assert_not_called()
        saved = load_harness_config(self.root / '.fruitfly/config.yaml').select()
        remote = next(m for m in saved.mechanisms if m.mechanism_id == 'ssh-env')
        self.assertEqual(remote.parameters['host'], 'changed.example')
        self.assertIn('changed.example', output.getvalue())
        self.assertFalse((self.root / '.fruitfly/sessions').exists())

    async def test_cleanup_failure_aborts_instead_of_offering_another_attempt(self):
        async def fail_close(backend):
            raise RuntimeError('fixture cleanup failed')
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(cli, 'RunApplicationFactory', return_value=self.factory), patch.object(
                SshEnv, '_connect', side_effect=OSError('fixture unreachable')) as connection, patch.object(
                SshEnv, 'close', fail_close), patch('sys.stdin', io.StringIO('1\n1\n')), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            self.assertEqual(await cli.run_cli(_args(cwd=str(self.root))), 2)
        self.assertEqual(connection.call_count, 1)
        self.assertIn('cleanup failed', errors.getvalue())
        self.assertNotIn('Startup failed', output.getvalue())
