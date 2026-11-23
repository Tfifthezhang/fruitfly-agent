"""Subscription drafts use the existing configuration and runtime lifecycle."""
import io
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, patch
from fruitfly_agent.run import RunApplicationFactory
from fruitfly_agent.providers.registry import default_registry, load_model_specs
from fruitfly_agent.interactive import TerminalConfigurationFrontend
from tests.support.connections import connection_service, account_record, seed_directory
from tests.support.provider_streams import SDKStream
from tests.support.terminal import ScriptedLines

class ModelConnectionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.service = connection_service(self.root / 'user')
        self.service.credentials().modify('account-a', lambda _: account_record(integration='opencode-go'))
        seed_directory(self.service, count=20)
        self.registry = default_registry()
        self.registry.credential_store = self.service.credentials()
        self.factory = RunApplicationFactory(cwd=self.root, user_root=(self.root) / '.fruitfly-user', environment={}, allow_incomplete=True,
            connection_service=self.service, provider_registry=self.registry)
        self.setup = self.factory.configuration.model_setup
        self.connections = self.setup.connections

    def test_selected_model_only_is_saved_and_discard_preserves_account(self):
        self.connections.stage('opencode-go', 'account-a', 'model-1', 'daily')
        self.assertTrue(self.factory.configuration.snapshot().ready)
        self.assertFalse((self.root / '.fruitfly/models.yaml').exists())
        self.factory.configuration.reset()
        self.assertTrue(self.service.ready('opencode-go', 'account-a'))
        self.assertFalse(self.setup.changed)
        self.connections.stage('opencode-go', 'account-a', 'model-2', 'daily')
        self.factory.configuration.save()
        catalog = self.root / '.fruitfly/models.yaml'
        self.assertEqual(set(load_model_specs(catalog, catalog.with_name('subscriptions.yaml'))), {'daily'})
        self.assertEqual(catalog.read_text(), 'models: {}\n')
        text = catalog.with_name('subscriptions.yaml').read_text()
        self.assertIn('connection:', text)
        self.assertNotIn('access_token', text)
        self.assertNotIn('offline-token', text)
        self.factory.reload_configuration()
        self.assertTrue(self.factory.configuration.snapshot().ready)

    def test_unreferenced_neighbor_does_not_enter_model_roles(self):
        from dataclasses import replace
        self.connections.stage('opencode-go', 'account-a', 'model-0', 'daily')
        self.factory.configuration.save()
        profile = self.factory.configuration.profile()
        self.assertEqual(profile.subscription_catalog, 'subscriptions.yaml')
        self.assertIn('daily', self.setup.models(profile))
        self.assertNotIn('daily', self.setup.models(replace(profile, subscription_catalog=None)))

    def test_wizard_stages_key_variable_and_only_confirmed_model_options(self):
        from dataclasses import replace
        self.setup.environment['OPENCODE_GO_KEY'] = 'offline-go-token'
        account = self.connections.use_key_variable('opencode-go', 'OPENCODE_GO_KEY')
        snapshot = seed_directory(self.service, account=account)
        scope = self.service.scope('opencode-go', account)
        row = {**snapshot.models[0], 'options': {'reasoning_effort': ['high']}}
        self.service.cache.write(scope, replace(snapshot, models=(row,)), complete=True)
        with self.assertRaisesRegex(ValueError, 'does not confirm'):
            self.connections.stage('opencode-go', account, 'model-0', 'daily',
                                   parameters={'reasoning_effort': 'low'})
        self.assertFalse(self.setup.changed)
        self.connections.stage('opencode-go', account, 'model-0', 'daily',
                               parameters={'reasoning_effort': 'high'})
        self.factory.configuration.save()
        catalog = self.root / '.fruitfly/subscriptions.yaml'
        spec = load_model_specs(catalog)['daily']
        self.assertEqual(spec.parameters, {'reasoning_effort': 'high'})
        self.assertEqual(spec.access['credential'], {'env': 'OPENCODE_GO_KEY'})
        self.assertNotIn('offline-go-token', catalog.read_text())

    def test_workspace_secret_file_makes_environment_connection_ready(self):
        import yaml
        from fruitfly_agent.providers.config import load_env

        self.connections.stage('opencode-go', 'account-a', 'model-0', 'daily')
        self.factory.configuration.save()
        directory = self.root / '.fruitfly'
        catalog = directory / 'subscriptions.yaml'
        document = yaml.safe_load(catalog.read_text())
        connection = next(iter(document['connections'].values()))
        connection.pop('account')
        connection['credential'] = {'env': 'OPENCODE_GO_KEY'}
        catalog.write_text(yaml.safe_dump(document))
        secret_file = directory / 'secrets.env'
        secret_file.write_text('OPENCODE_GO_KEY=offline-go-token\n')
        secret_file.chmod(0o600)
        factory = RunApplicationFactory(cwd=self.root, user_root=(self.root) / '.fruitfly-user', environment=load_env(secret_file), allow_incomplete=True)
        self.assertTrue(factory.configuration.snapshot().ready)
        self.assertNotIn('offline-go-token', catalog.read_text())

    def test_export_preserves_subscription_alias_and_does_not_copy_secrets(self):
        from fruitfly_agent.run.configuration.export import export_configuration
        self.connections.stage('opencode-go', 'account-a', 'model-0', 'daily')
        self.factory.configuration.save()
        destination = self.root.resolve() / 'export'
        export_configuration(self.root / '.fruitfly/config.yaml', destination, apply=True)
        exported = load_model_specs(destination / 'models.yaml', destination / 'subscriptions.yaml')
        self.assertEqual(exported['daily'].model, 'model-0')
        self.assertNotIn('offline-token', (destination / 'subscriptions.yaml').read_text())
        self.assertFalse((destination / 'secrets.env').exists())

    def test_first_api_model_can_be_added_after_subscription_only_setup(self):
        self.connections.stage('opencode-go', 'account-a', 'model-0', 'daily')
        self.factory.configuration.save()
        primary = self.root / '.fruitfly/models.yaml'
        companion = primary.with_name('subscriptions.yaml')
        saved = companion.read_bytes()
        self.setup.stage('openai', dict(profile='api', model='offline-model', base_url='',
            context_window='8192', max_output_tokens='1024', api_key_env=''), 'fixture-api-key')
        self.factory.configuration.save()
        self.assertEqual(set(load_model_specs(primary, companion)), {'api', 'daily'})
        self.assertEqual(companion.read_bytes(), saved)

    def test_cancelled_selection_and_concurrent_source_change_do_not_publish(self):
        self.connections.stage('opencode-go', 'account-a', 'model-1', 'daily')
        catalog = self.root / '.fruitfly/models.yaml'
        catalog.parent.mkdir(parents=True, exist_ok=True)
        catalog.write_text('models: {}\nmetadata: {authored: true}\n')
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.factory.configuration.save()
        self.assertIn('authored: true', catalog.read_text())

    def test_search_favorites_and_recent_do_not_expand_project_configuration(self):
        self.assertEqual(len(self.connections.models('opencode-go', 'account-a')), 20)
        self.assertEqual(len(self.connections.models('opencode-go', 'account-a', 'model-19')), 1)
        self.connections.toggle_favorite('opencode-go', 'account-a', 'model-19')
        self.assertEqual(self.connections.models('opencode-go', 'account-a')[0].id, 'model-19')
        self.assertFalse(self.setup.changed)
        self.connections.stage('opencode-go', 'account-a', 'model-3', 'daily')
        self.assertTrue(next(m for m in self.connections.models('opencode-go', 'account-a') if m.id == 'model-3').recent)

    def test_menu_can_select_a_cached_subscription_model_without_network(self):
        output = io.StringIO()
        # Subscription, Go, saved account, model, Use model, alias, Stage, save/start.
        frontend = TerminalConfigurationFrontend(self.factory.configuration, input_stream=io.StringIO(),
            output_stream=output, line_editor=ScriptedLines('2', '1', '1', '1', '1', 'daily', '2', '1'))
        with patch('httpx.get') as network:
            result = frontend.run()
        self.assertTrue(result.saved)
        network.assert_not_called()
        self.assertEqual(load_model_specs(self.root / '.fruitfly/models.yaml', self.root / '.fruitfly/subscriptions.yaml')['daily'].model, 'model-0')
        self.assertIn('Subscription · OpenCode Go', output.getvalue())

    async def test_saved_subscription_assembles_and_reports_real_usage_without_key_environment(self):
        self.connections.stage('opencode-go', 'account-a', 'model-0', 'daily')
        self.factory.configuration.save()
        self.factory.reload_configuration()
        usage = NS(prompt_tokens=12, completion_tokens=4, prompt_tokens_details=None, completion_tokens_details=None,
            opencode={'billing_source': 'go', 'allowance': .01}, cost=0)
        stream = SDKStream([NS(choices=[NS(index=0, finish_reason='stop', delta=NS(content='done'))], usage=usage)])
        client = NS(base_url='https://opencode.ai/inference/go/v1', close=AsyncMock(),
            chat=NS(completions=NS(create=AsyncMock(return_value=stream))))
        with patch('openai.AsyncOpenAI', return_value=client):
            handle = await self.factory.open(resume=False, session_path=self.root / 'session.jsonl')
        try:
            result = await handle.session.submit('hello')
            self.assertFalse(result.is_error)
            self.assertEqual(result.messages[-1].usage.input_tokens, 12)
            request = client.chat.completions.create.call_args.kwargs
            self.assertIn('x-opencode-session', request['extra_headers'])
            self.assertEqual(client.api_key, 'offline-token-a')
            self.assertNotIn('offline-token-a', (self.root / 'session.jsonl').read_text())
        finally:
            await handle.close()

    def test_second_model_reuses_connection_and_explicit_limit_update_preserves_authored_options(self):
        self.connections.stage('opencode-go', 'account-a', 'model-0', 'daily')
        self.factory.configuration.save()
        catalog = self.root / '.fruitfly/models.yaml'
        catalog = catalog.with_name('subscriptions.yaml')
        catalog.write_text('# authored header\n' + catalog.read_text().replace(
            '    model: model-0\n', '    model: model-0\n    parameters: {temperature: 0.2} # keep option\n'))
        self.connections.stage('opencode-go', 'account-a', 'model-1', 'secondary')
        self.factory.configuration.save()
        import yaml
        self.assertEqual(len(yaml.safe_load(catalog.read_text())['connections']), 1)
        seed_directory(self.service, count=20)
        self.connections.stage('opencode-go', 'account-a', 'model-0', 'daily', 4096, 1024)
        self.factory.configuration.save()
        models = load_model_specs(catalog)
        self.assertEqual(models['daily'].context_window, 4096)
        self.assertEqual(models['daily'].parameters, {'temperature': .2})
        self.assertIn('# authored header', catalog.read_text())
        self.assertIn('# keep option', catalog.read_text())
        self.connections.edit_parameters('daily', {'temperature': .4})
        self.assertEqual(load_model_specs(catalog)['daily'].parameters, {'temperature': .2})
        self.factory.configuration.save()
        self.assertEqual(load_model_specs(catalog)['daily'].parameters, {'temperature': .4})
        self.assertIn('# keep option', catalog.read_text())


    def test_chatgpt_cannot_reserve_a_smaller_unenforced_output_limit(self):
        self.service.credentials().modify('chat-account', lambda _: account_record(account='chat-account'))
        seed_directory(self.service, integration='chatgpt', account='chat-account')
        with self.assertRaisesRegex(ValueError, 'cannot enforce'):
            self.connections.stage('chatgpt', 'chat-account', 'model-0', 'unsafe', 8192, 32)
        self.assertFalse(self.setup.changed)


    def test_subscription_credential_action_opens_account_management_without_secret_input(self):
        from fruitfly_agent.interactive.terminal.features.configuration.model_setup import configure_credential
        self.connections.stage('opencode-go', 'account-a', 'model-0', 'daily')
        self.assertEqual(self.setup.authentication_kind('daily'), 'account')
        frontend = TerminalConfigurationFrontend(self.factory.configuration, input_stream=io.StringIO(),
            output_stream=io.StringIO(), line_editor=ScriptedLines())
        with patch('fruitfly_agent.interactive.terminal.features.configuration.model_connections.manage_connections') as manage:
            configure_credential(frontend._model_form(), self.setup, 'daily')
        manage.assert_called_once()
        self.assertEqual(frontend.input.tell(), 0)
