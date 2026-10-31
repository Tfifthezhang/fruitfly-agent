"""SSH selection, secret boundaries and Application lifecycle without network."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from fruitfly_agent.core.session import Session
from fruitfly_agent.interactive import AgentApplication
from fruitfly_agent.interactive.contracts.commands import InteractiveCommand
from fruitfly_agent.interactive.interaction.commands import CommandRouter
from fruitfly_agent.interactive.terminal.rendering.welcome import render_welcome
from fruitfly_agent.lab.catalog import builtin_catalog, MechanismSelection
from fruitfly_agent.lab.environment.ssh import SshEnv
from fruitfly_agent.run import build_runtime
from fruitfly_agent.run.adapters.runtime import describe_runtime
from fruitfly_agent.run.application import RunApplicationFactory, record_session_manifest
from fruitfly_agent.run.configuration import HarnessProfile, load_harness_config
from tests.support.faux_provider import FauxProvider
from tests.support.run import _write_catalog
from tests.support.ssh import SftpFixture


class SshRunTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        _write_catalog(self.root / '.fruitfly/models.yaml', {'offline': 'offline-model'})
        self.registry = Mock()
        self.registry.create.return_value = FauxProvider()
        self.secrets = {'FRUITFLY_SSH_USERNAME': 'fixture-private-account',
                        'FRUITFLY_SSH_PASSWORD': 'fixture-private-password',
                        'TEST_API_KEY': 'fixture-model-secret'}

    def factory(self):
        factory = RunApplicationFactory(cwd=self.root, environment=self.secrets, provider_registry=self.registry)
        factory.configuration.set_mechanism('working-memory-reduction', enabled=False)
        factory.configuration.set_mechanism('ssh-env', enabled=True)
        factory.configuration.set_parameter('ssh-env', 'host', 'server.example')
        factory.configuration.set_parameter('ssh-env', 'port', '2222')
        factory.configuration.set_parameter('ssh-env', 'cwd', '/srv/project')
        factory.configuration.save()
        factory.reload_configuration()
        return factory

    async def test_configuration_menu_switches_environment_and_persists_only_secret_names(self):
        factory = self.factory()
        snapshot = factory.configuration.snapshot()
        self.assertTrue(snapshot.ready, snapshot.warnings)
        views = {item.mechanism_id: item for item in snapshot.mechanisms}
        self.assertEqual('Local environment', views['local-env'].label)
        self.assertEqual('Remote environment', views['ssh-env'].label)
        self.assertIn('SSH', views['ssh-env'].description)
        profile = factory.configuration.profile()
        enabled = {m.mechanism_id for m in profile.mechanisms if m.enabled}
        self.assertIn('ssh-env', enabled)
        self.assertTrue({'read-tool', 'write-tool', 'edit-tool', 'bash-tool'} <= enabled)
        self.assertFalse({'local-env', 'memory-files', 'ipython-tool'} & enabled)
        factory.configuration.save()
        text = (self.root / '.fruitfly/config.yaml').read_text()
        for secret in self.secrets.values():
            self.assertNotIn(secret, text)
        for name in ('FRUITFLY_SSH_USERNAME', 'FRUITFLY_SSH_PASSWORD'):
            self.assertIn(name, text)
        saved = load_harness_config(self.root / '.fruitfly/config.yaml').select()
        remote = next(m for m in saved.mechanisms if m.mechanism_id == 'ssh-env')
        self.assertEqual(2222, remote.parameters['port'])
        self.assertEqual('/srv/project', remote.parameters['cwd'])
        factory.configuration.set_mechanism('local-env', enabled=True)
        enabled = {m.mechanism_id for m in factory.configuration.profile().mechanisms if m.enabled}
        self.assertIn('local-env', enabled)
        self.assertNotIn('ssh-env', enabled)

    async def test_environment_display_tracks_activation_and_retains_previous_target_on_failure(self):
        factory = self.factory()
        app = AgentApplication(factory)
        self.addAsyncCleanup(app.close)
        server = self.root / 'server-fixture'
        (server / 'srv/project').mkdir(parents=True)
        def connect(backend):
            if backend.config.host == 'unavailable.example':
                raise OSError('fixture startup failed')
            return Mock(), SftpFixture(server)
        def display():
            status = app.status
            self.assertEqual(str(self.root.resolve()), status.working_directory)
            return '\n'.join((render_welcome(status, columns=100, terminal_ui=True, color=False),
                CommandRouter().execute(InteractiveCommand('lab'), app).text,
                CommandRouter().execute(InteractiveCommand('status'), app).text))
        with patch.object(SshEnv, '_connect', autospec=True, side_effect=connect) as connection:
            await app.start()
            initial = app.status.execution_environment
            self.assertEqual('Remote SSH', initial.label)
            self.assertEqual('server.example:2222', initial.server)
            self.assertEqual('/srv/project', initial.working_directory)
            for token in (str(self.root.resolve()), 'server.example:2222', '/srv/project', 'Remote SSH'):
                self.assertGreaterEqual(display().count(token), 3)
            for secret in self.secrets.values():
                self.assertNotIn(secret, display())
            self.assertEqual(1, connection.call_count, 'inspection must not reconnect')
            factory.configuration.set_parameter('ssh-env', 'host', 'unavailable.example')
            self.assertEqual(initial, app.status.execution_environment, 'a draft is not active')
            factory.configuration.save()
            self.assertEqual(initial, app.status.execution_environment, 'saving alone does not activate')
            with self.assertRaisesRegex(RuntimeError, 'SSH connection failed'):
                await app.apply_configuration()
            self.assertEqual(initial, app.status.execution_environment)
            self.assertNotIn('unavailable.example', display())
            factory.configuration.set_parameter('ssh-env', 'host', 'replacement.example')
            factory.configuration.save()
            await app.apply_configuration()
            self.assertEqual('replacement.example:2222', app.status.execution_environment.server)
            self.assertNotIn('server.example', display())
            factory.configuration.set_mechanism('local-env', enabled=True)
            factory.configuration.save()
            await app.apply_configuration()
            local = app.status.execution_environment
            self.assertEqual('Local', local.label)
            self.assertEqual(str(self.root.resolve()), local.working_directory)
            self.assertEqual('', local.server)
            self.assertNotIn('replacement.example', display())
            self.assertEqual([], self.registry.create.return_value.calls)

    async def test_assembly_is_offline_and_secret_rotation_does_not_serialize_credentials(self):
        profile = HarnessProfile('remote', str(self.root / '.fruitfly/models.yaml'), 'offline', (
            MechanismSelection('ssh-env', parameters={'host': 'server.example', 'port': 2222}),
            MechanismSelection('read-tool'), MechanismSelection('bash-tool')))
        digests = []
        with patch.object(SshEnv, '_connect', side_effect=AssertionError('construction made SSH request')):
            for index, suffix in enumerate(('a', 'b')):
                environment = {name: value + suffix for name, value in self.secrets.items()}
                with Session(self.root / f'session-{index}.jsonl') as session:
                    runtime = build_runtime(profile, config_path=self.root / 'config.yaml', catalog=builtin_catalog(),
                        environment=environment, cwd=self.root, session=session, provider_registry=self.registry)
                    self.assertEqual('ssh-permissions-v1', runtime.manifest.permissions['implementation'])
                    self.assertEqual(2222, runtime.manifest.permissions['port'])
                    self.assertEqual('/srv/workspace', runtime.config.env.cwd)
                    _, details, _ = describe_runtime(runtime, builtin_catalog())
                    remote = next(item for item in details if item.mechanism_id == 'ssh-env')
                    self.assertEqual('Remote environment', remote.label)
                    self.assertEqual('environment', remote.category)
                    record_session_manifest(session, runtime)
                    text = json.dumps(runtime.manifest.to_dict()) + session.path.read_text()
                    for secret in environment.values():
                        self.assertNotIn(secret, text)
                        self.assertNotIn(secret, runtime.config.system_prompt)
                    self.assertIn('FRUITFLY_SSH_USERNAME', text)
                    self.assertIn('FRUITFLY_SSH_PASSWORD', text)
                    digests.append(runtime.manifest.digest)
                    await runtime.components['ssh-environment'].close()
        self.assertEqual(digests[0], digests[1])

    async def test_missing_secret_and_disabled_backend_make_no_connections(self):
        factory = self.factory()
        factory.environment.pop('FRUITFLY_SSH_PASSWORD')
        with patch.object(SshEnv, '_connect') as connect:
            app = AgentApplication(factory)
            self.addAsyncCleanup(app.close)
            with self.assertRaisesRegex(ValueError, 'secret environment'):
                await app.start()
            connect.assert_not_called()
        factory.configuration.set_mechanism('ssh-env', enabled=False)
        factory.configuration.set_mechanism('local-env', enabled=True)
        factory.configuration.save()
        factory.reload_configuration()
        with patch.object(SshEnv, '_connect') as connect:
            await app.start()
            connect.assert_not_called()
            await app.close()

    async def test_application_file_tools_use_remote_workspace_and_resume_opens_fresh_connection(self):
        server = self.root / 'server-fixture'
        server.mkdir()
        (server / 'srv/project').mkdir(parents=True)
        connections = []
        def connect(backend):
            sftp = SftpFixture(server)
            client = Mock()
            connections.append((client, sftp))
            return client, sftp
        factory = self.factory()
        factory.configuration.save()
        factory.reload_configuration()
        app = AgentApplication(factory)
        self.addAsyncCleanup(app.close)
        provider = self.registry.create.return_value
        path = self.root / '.fruitfly/sessions/remote.jsonl'
        with patch.object(SshEnv, '_connect', connect):
            await app.start(session_path=path)
            provider.respond_tool_call('write', {'path': 'hello.txt', 'content': 'remote hello'})
            provider.respond_tool_call('edit', {'path': 'hello.txt', 'edits': [{'oldText': 'hello', 'newText': 'world'}]})
            provider.respond_tool_call('read', {'path': 'hello.txt'})
            provider.respond_text('Done')
            result = await app.submit('Write, edit and read the remote file.')
            self.assertFalse(result.is_error)
            messages = [m for m in result.messages if m.role == 'toolResult']
            self.assertEqual(3, len(messages))
            self.assertTrue(all(not m.is_error for m in messages), [m.text for m in messages])
            self.assertEqual('remote world', messages[-1].text)
            self.assertEqual('remote world', (server / 'srv/project/hello.txt').read_text())
            self.assertFalse((self.root / 'hello.txt').exists())
            await app.close()
            factory.configuration.set_parameter('ssh-env', 'host', 'resumed.example')
            factory.configuration.set_parameter('ssh-env', 'port', '2223')
            factory.configuration.set_parameter('ssh-env', 'cwd', '/srv/resumed')
            (server / 'srv/resumed').mkdir()
            factory.configuration.save()
            factory.reload_configuration()
            await app.start(resume=True, session_path=path)
            self.assertEqual('resumed.example:2223', app.status.execution_environment.server)
            self.assertEqual('/srv/resumed', app.status.execution_environment.working_directory)
            self.assertEqual(str(self.root.resolve()), app.status.working_directory)
            self.assertEqual(2, len(connections))
            await app.close()
        for client, sftp in connections:
            client.close.assert_called_once()
            self.assertTrue(sftp.closed)
        for secret in self.secrets.values():
            self.assertNotIn(secret, path.read_text())

    async def test_owned_backend_is_closed_when_later_assembly_or_startup_fails(self):
        for failure in ('assembly', 'startup'):
            with self.subTest(failure=failure):
                factory = self.factory()
                app = AgentApplication(factory)
                created = []
                original_init = SshEnv.__init__
                def capture(backend, *args, **kwargs):
                    original_init(backend, *args, **kwargs)
                    created.append(backend)
                self.addAsyncCleanup(app.close)
                with patch.object(SshEnv, '__init__', capture), patch.object(SshEnv, '_connect', side_effect=OSError('fixture-private-password')) as connect:
                    if failure == 'assembly':
                        with patch('fruitfly_agent.lab.catalog.builtins.create_read_tool', side_effect=ValueError('fixture assembly failure')):
                            with self.assertRaisesRegex(ValueError, 'assembly failure'):
                                await app.start()
                        connect.assert_not_called()
                    else:
                        with self.assertRaisesRegex(RuntimeError, 'SSH connection failed'):
                            await app.start()
                self.assertEqual(1, len(created))
                self.assertTrue(created[0]._closed)
                self.assertEqual('', created[0]._password)

    async def test_documented_template_parses_and_resolves_offline(self):
        template = Path(__file__).resolve().parents[2] / 'examples/configuration/ssh.example.yaml'
        profile = load_harness_config(template).select()
        resolved = builtin_catalog().resolve(profile.mechanisms)
        self.assertEqual({'ssh-env', 'read-tool', 'write-tool', 'edit-tool', 'bash-tool'},
                         {item.definition.descriptor.mechanism_id for item in resolved})
        ignore = (template.parents[2] / '.gitignore').read_text().splitlines()
        self.assertTrue({'.fruitfly/', '.env', '.env.*', 'secrets.env'} <= set(ignore))
