"""Hidden web credentials follow pending service choices and the shared save transaction."""
import asyncio
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from fruitfly_agent.interactive import AgentApplication, TerminalConfigurationFrontend
from fruitfly_agent.interactive.terminal.features.configuration.mechanism_setup import run_mechanism_setup
from fruitfly_agent.providers.config import load_env
from fruitfly_agent.run import RunApplicationFactory
from tests.support.faux_provider import FauxProvider
from tests.support.run import _write_catalog
from tests.support.terminal import MenuScriptedLines


class WebSetupTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        _write_catalog(self.root / '.fruitfly/models.yaml', {'offline': 'offline-model'})
        self.provider = FauxProvider()
        registry = Mock()
        registry.create.return_value = self.provider
        self.factory = RunApplicationFactory(cwd=self.root, environment={'TEST_API_KEY': 'fixture-model-key'}, provider_registry=registry)
        self.configuration = self.factory.configuration
        self.service = self.configuration.mechanism_setup
        self.output = io.StringIO()

    def frontend(self, *lines, secrets='fixture-search-secret\n'):
        reader = MenuScriptedLines(self.output, *lines)
        reader.offset = len(self.output.getvalue())
        return TerminalConfigurationFrontend(self.configuration, input_stream=io.StringIO(secrets),
            output_stream=self.output, line_editor=reader)

    def wizard(self, mechanism, *lines, secrets='fixture-search-secret\n'):
        frontend = self.frontend(*lines, secrets=secrets)
        return run_mechanism_setup(frontend._model_form(), self.service, mechanism)

    def assert_hidden(self, *values):
        for value in values:
            self.assertNotIn(value, self.output.getvalue())
            self.assertNotIn(value, repr(self.configuration.snapshot()))
            path = self.root / '.fruitfly/config.yaml'
            if path.exists():
                self.assertNotIn(value, path.read_text())

    def test_registered_extension_appears_in_the_same_wizard_without_frontend_changes(self):
        from fruitfly_agent.lab.catalog import LabCatalog, builtin_catalog
        from fruitfly_agent.lab.tools.web import default_service_registry, WebServiceDefinition, WebServiceRegistry
        from fruitfly_agent.lab.tools.web.registration import definitions
        base = default_service_registry()
        extended = WebServiceRegistry(
            search=tuple(base.get('search', name) for name in base.choices('search')) +
                (WebServiceDefinition('fixture', lambda client, key: None, 'FIXTURE_SEARCH_KEY'),),
            fetch=tuple(base.get('fetch', name) for name in base.choices('fetch')))
        builtin = builtin_catalog()
        replacements = definitions(extended)
        replaced = {d.descriptor.mechanism_id for d in replacements}
        catalog = LabCatalog(tuple(d for d in builtin.definitions() if d.descriptor.mechanism_id not in replaced) +
            replacements, bootstrap=builtin.bootstrap)
        factory = RunApplicationFactory(cwd=self.root, environment={'TEST_API_KEY': 'fixture-model-key'}, catalog=catalog)
        frontend = TerminalConfigurationFrontend(factory.configuration, input_stream=io.StringIO('fixture-key\n'),
            output_stream=self.output, line_editor=MenuScriptedLines(self.output, '@fixture', '', '@Stage settings'))
        self.assertTrue(run_mechanism_setup(frontend._model_form(), factory.configuration.mechanism_setup, 'web-search-tool'))
        selection = next(m for m in factory.configuration.profile().mechanisms if m.mechanism_id == 'web-search-tool')
        self.assertEqual('fixture', selection.parameters['backend'])
        self.assertIn('FIXTURE_SEARCH_KEY', self.output.getvalue())
        self.assertNotIn('fixture-key', self.output.getvalue())
        self.assertFalse((self.root / '.fruitfly/secrets.env').exists())

    def test_choice_cancel_keeps_profile_and_credentials_untouched(self):
        before = self.configuration.profile()
        self.assertFalse(self.wizard('web-search-tool', 'back', secrets=''))
        self.assertEqual(before, self.configuration.profile())
        self.assertFalse(self.service.credentials.available('BRAVE_SEARCH_API_KEY'))

    def test_expanded_parameter_uses_the_same_service_choices(self):
        self.factory.environment.update(BRAVE_SEARCH_API_KEY='fixture-brave', TAVILY_API_KEY='fixture-tavily')
        self.configuration.set_mechanism('web-search-tool', enabled=True)
        frontend = self.frontend('@Tools', '@Search the web', '@Search service', '@tavily',
            'back', 'back', 'back', '@Save only', secrets='')
        self.assertTrue(frontend.run_for_active_session().saved)
        selection = next(m for m in self.configuration.profile().mechanisms if m.mechanism_id == 'web-search-tool')
        self.assertEqual('tavily', selection.parameters['backend'])
        self.assertTrue(selection.enabled)
        self.assertFalse((self.root / '.fruitfly/secrets.env').exists())

    def test_interactive_search_selects_new_service_and_saves_hidden_key(self):
        frontend = self.frontend('@Configure', '@Tools', '@Search the web', 'space',
            '@deepseek', '', '@Stage settings', 'back', 'back', 'back', '@Start new session')
        result = frontend.run()
        self.assertTrue(result.start)
        self.assertTrue(result.saved)
        path = self.root / '.fruitfly/secrets.env'
        self.assertEqual({'DEEPSEEK_SEARCH_API_KEY': 'fixture-search-secret'}, load_env(path))
        self.assertEqual(0o600, path.stat().st_mode & 0o777)
        self.assertEqual('fixture-search-secret', self.factory.environment['DEEPSEEK_SEARCH_API_KEY'])
        selection = next(m for m in self.configuration.profile().mechanisms if m.mechanism_id == 'web-search-tool')
        self.assertEqual('deepseek', selection.parameters['backend'])
        self.assertNotIn('BRAVE_SEARCH_API_KEY', self.factory.environment)
        self.assertIn('DEEPSEEK_SEARCH_API_KEY', self.output.getvalue())
        self.assertIn('API key: entered (value hidden)', self.output.getvalue())
        self.assert_hidden('fixture-search-secret')
        async def start():
            app = AgentApplication(self.factory)
            try:
                with patch('fruitfly_agent.lab.tools.web.WebClient.request', side_effect=AssertionError('setup sent HTTP')):
                    await app.start(session_path=self.root / '.fruitfly/sessions/setup.jsonl')
            finally:
                await app.close()
        asyncio.run(start())
        self.assertEqual([], self.provider.calls)

    def test_interactive_fetch_switches_from_direct_and_saves_separate_key(self):
        frontend = self.frontend('@Configure', '@Tools', '@Fetch web pages', '@Set up…',
            '@deepseek', '', '@Stage settings', 'back', 'back', 'back', '@Start new session',
            secrets='fixture-fetch-secret\n')
        self.assertTrue(frontend.run().saved)
        values = load_env(self.root / '.fruitfly/secrets.env')
        self.assertEqual({'DEEPSEEK_FETCH_API_KEY': 'fixture-fetch-secret'}, values)
        self.assertIn('Step 3 of 3', self.output.getvalue())
        self.assert_hidden('fixture-fetch-secret')

    def test_custom_variable_validation_uses_current_form_values(self):
        self.factory.environment['CUSTOM_SEARCH_KEY'] = 'fixture-existing-key'
        self.assertTrue(self.wizard('web-search-tool', '@deepseek', 'CUSTOM_SEARCH_KEY', '@Stage settings', secrets='\n'))
        self.configuration.save()
        selection = next(m for m in self.configuration.profile().mechanisms if m.mechanism_id == 'web-search-tool')
        self.assertEqual('CUSTOM_SEARCH_KEY', selection.parameters['api_key_env'])
        self.assertFalse((self.root / '.fruitfly/secrets.env').exists(), 'blank reuses the environment without serializing its value')
        self.assertIn('API key: reused (value hidden)', self.output.getvalue())
        self.assert_hidden('fixture-existing-key')

    def test_clearing_previous_service_override_uses_new_service_default(self):
        self.configuration.set_parameter('web-search-tool', 'api_key_env', 'BRAVE_SEARCH_API_KEY')
        self.assertTrue(self.wizard('web-search-tool', '@deepseek', '/clear', '@Stage settings'))
        self.configuration.save()
        self.assertEqual({'DEEPSEEK_SEARCH_API_KEY': 'fixture-search-secret'}, load_env(self.root / '.fruitfly/secrets.env'))

    def test_switching_fetch_to_direct_skips_key_and_rejects_stale_secret_submission(self):
        self.configuration.set_parameter('web-fetch-tool', 'backend', 'deepseek')
        with patch('fruitfly_agent.interactive.terminal.features.configuration.mechanism_setup.read_secret',
                   side_effect=AssertionError('direct fetch requested a key')):
            self.assertTrue(self.wizard('web-fetch-tool', '@direct', '', '@Stage settings', secrets=''))
        self.assertEqual((), self.service.form('web-fetch-tool').credentials)
        self.configuration.save()
        self.assertFalse((self.root / '.fruitfly/secrets.env').exists())
        with self.assertRaisesRegex(ValueError, 'Unknown credential input'):
            self.service.stage('web-fetch-tool', {'backend': 'direct'}, {'api_key_env': 'fixture-stale-key'})

    def test_service_defaults_are_resolved_for_search_and_fetch_without_mutation(self):
        before = self.configuration.profile()
        for mechanism, backend, variable in (
            ('web-search-tool', 'brave', 'BRAVE_SEARCH_API_KEY'),
            ('web-search-tool', 'tavily', 'TAVILY_API_KEY'),
            ('web-search-tool', 'deepseek', 'DEEPSEEK_SEARCH_API_KEY'),
            ('web-fetch-tool', 'deepseek', 'DEEPSEEK_FETCH_API_KEY'),
        ):
            with self.subTest(mechanism=mechanism, backend=backend):
                form = self.service.form(mechanism, {'backend': backend})
                self.assertEqual(1, len(form.credentials))
                self.assertIn(variable, form.credentials[0].description)
                self.assertFalse(form.credentials[0].available)
        self.assertEqual(before, self.configuration.profile())

    def test_cancel_eof_and_interrupt_leave_no_staged_key_or_configuration(self):
        before = self.configuration.profile()
        for lines, secrets in (
            (('@deepseek', '/cancel'), ''),
            (('@deepseek', ''), '/cancel\n'),
            (('@deepseek', ''), ''),
            (('@deepseek', '', '@Cancel'), 'fixture-cancelled-key\n'),
        ):
            with self.subTest(lines=lines, secrets=bool(secrets)):
                self.assertFalse(self.wizard('web-search-tool', *lines, secrets=secrets))
                self.assertEqual(before, self.configuration.profile())
                self.assertFalse(self.service.credentials.available('DEEPSEEK_SEARCH_API_KEY'))
                self.assertFalse((self.root / '.fruitfly/secrets.env').exists())
                self.assertFalse((self.root / '.fruitfly/config.yaml').exists())
        with patch('fruitfly_agent.interactive.terminal.features.configuration.mechanism_setup.read_secret', side_effect=KeyboardInterrupt):
            self.assertFalse(self.wizard('web-search-tool', '@deepseek', '', secrets=''))
        self.assertEqual(before, self.configuration.profile())
        self.assert_hidden('fixture-cancelled-key')

    def test_empty_invalid_and_conflicting_key_retry_without_echo(self):
        self.assertTrue(self.wizard('web-search-tool', '@deepseek', '', '@Stage settings',
                                   secrets='\nkey with spaces\nfixture-search-secret\n'))
        self.assertIn('API key is missing or conflicts', self.output.getvalue())
        self.assert_hidden('key with spaces', 'fixture-search-secret')
        self.configuration.reset()
        self.factory.environment['DEEPSEEK_SEARCH_API_KEY'] = 'fixture-original-key'
        self.output = io.StringIO()
        self.assertTrue(self.wizard('web-search-tool', '@deepseek', '', '@Stage settings',
                                   secrets='fixture-replacement-key\n\n'))
        self.assertIn('API key: reused', self.output.getvalue())
        self.assertEqual('fixture-original-key', self.factory.environment['DEEPSEEK_SEARCH_API_KEY'])
        self.assert_hidden('fixture-original-key', 'fixture-replacement-key')

    def test_shared_save_preserves_existing_content_rolls_back_and_updates_environment(self):
        path = self.root / '.fruitfly/secrets.env'
        path.parent.mkdir(exist_ok=True)
        original = '# Keep this comment\nUNRELATED=value\n'
        path.write_text(original)
        self.assertTrue(self.wizard('web-search-tool', '@deepseek', '', '@Stage settings'))
        self.assertTrue(self.wizard('web-fetch-tool', '@deepseek', '', '@Stage settings', secrets='fixture-fetch-secret\n'))
        self.assertEqual(original, path.read_text(), 'staging must not write keys')
        with patch('fruitfly_agent.run.configuration.controller.save_harness_config', side_effect=OSError('fixture save failure')):
            with self.assertRaises(OSError):
                self.configuration.save()
        self.assertEqual(original, path.read_text())
        self.assertNotIn('DEEPSEEK_SEARCH_API_KEY', self.factory.environment)
        self.assertTrue(self.configuration.changed)
        self.configuration.save()
        self.assertTrue(path.read_text().startswith(original))
        self.assertEqual({'UNRELATED': 'value', 'DEEPSEEK_SEARCH_API_KEY': 'fixture-search-secret',
                          'DEEPSEEK_FETCH_API_KEY': 'fixture-fetch-secret'}, load_env(path))
        self.assertEqual(0o600, path.stat().st_mode & 0o777)
        self.assert_hidden('fixture-search-secret', 'fixture-fetch-secret')

    def test_discard_removes_staged_key_without_touching_files(self):
        before = self.configuration.profile()
        self.assertTrue(self.wizard('web-search-tool', '@deepseek', '', '@Stage settings'))
        self.assertTrue(self.service.credentials.available('DEEPSEEK_SEARCH_API_KEY'))
        self.configuration.reset()
        self.assertEqual(before, self.configuration.profile())
        self.assertFalse(self.service.credentials.available('DEEPSEEK_SEARCH_API_KEY'))
        self.assertFalse((self.root / '.fruitfly/secrets.env').exists())
