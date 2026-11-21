"""Catalog refresh and strict connected-model resolution are offline."""
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import httpx
import yaml
from fruitfly_agent.providers.registry import load_model_specs
from fruitfly_agent.providers.specs import ModelSpec
from tests.support.connections import connection_service, account_record, seed_directory

class ConnectionTests(unittest.TestCase):
    def test_variable_directory_scope_survives_restart_and_changes_with_key(self):
        with tempfile.TemporaryDirectory() as directory:
            first = connection_service(directory)
            account = first.bind_variable('opencode-go', 'GO_KEY', {'GO_KEY': 'fixture-a'})
            original_scope = first.scope('opencode-go', account)
            seed_directory(first, account=account)
            second = connection_service(directory)
            restored = second.bind_variable('opencode-go', 'GO_KEY', {'GO_KEY': 'fixture-a'})
            self.assertEqual(second.scope('opencode-go', restored), original_scope)
            self.assertIsNotNone(second.snapshot('opencode-go', restored))
            changed = second.bind_variable('opencode-go', 'GO_KEY', {'GO_KEY': 'fixture-b'})
            self.assertNotEqual(second.scope('opencode-go', changed), original_scope)
            self.assertIsNone(second.snapshot('opencode-go', changed))
            for path in (Path(directory) / 'auth' / 'bindings').glob('*.json'):
                self.assertNotIn('fixture-a', path.read_text())
                self.assertNotIn('fixture-b', path.read_text())
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_connected_config_and_frozen_model_round_trip_reject_route_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'models.yaml'
            entry = {'connection': 'work', 'model': 'model-a', 'context_window': 8192, 'max_output_tokens': 2048}
            value = {'connections': {'work': {'integration': 'chatgpt', 'account': 'account-a'}}, 'models': {'work': entry}}
            path.write_text(yaml.safe_dump(value))
            spec = load_model_specs(path)['work']
            self.assertEqual(ModelSpec.from_dict(spec.id, spec.to_dict()), spec)
            self.assertEqual(spec.output_reserve, 2048)
            self.assertEqual(spec.provider.api_key_env, '')
            for change in ({'base_url': 'https://fixture.invalid'}, {'api_key_env': 'OTHER'}, {'sdk': 'other'}, {'access': {}}):
                value['models']['work'] = {**entry, **change}
                path.write_text(yaml.safe_dump(value))
                with self.assertRaises(ValueError):
                    load_model_specs(path)

    def test_read_is_offline_and_conditional_refresh_preserves_models(self):
        with tempfile.TemporaryDirectory() as directory:
            service = connection_service(directory)
            service.credentials().modify('account-a', lambda _: account_record(integration='opencode-go'))
            snapshot = seed_directory(service, fetched_at=1)
            with patch('httpx.get', return_value=httpx.Response(304)) as get:
                self.assertEqual(service.snapshot('opencode-go', 'account-a'), snapshot)
                get.assert_not_called()
                service._fetch('opencode-go', 'account-a')
                self.assertEqual(get.call_args.kwargs['headers']['If-None-Match'], 'revision-a')
            updated = service.snapshot('opencode-go', 'account-a')
            self.assertEqual(updated.models, snapshot.models)
            self.assertGreater(updated.fetched_at, 1)
            with patch('httpx.get', return_value=httpx.Response(200, json={'data': [], 'has_more': True})):
                with self.assertRaises(ValueError):
                    service._fetch('opencode-go', 'account-a')
            self.assertEqual(service.snapshot('opencode-go', 'account-a'), updated)

    def test_refresh_merges_concurrency_and_backs_off_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            service = connection_service(directory)
            entered, release = threading.Event(), threading.Event()
            def fetch(*args):
                entered.set()
                release.wait(2)
                raise ValueError('offline')
            with patch.object(service, '_fetch', side_effect=fetch) as fetch_mock:
                service.refresh('opencode-go', 'account-a')
                self.assertTrue(entered.wait(1))
                for _ in range(10):
                    service.refresh('opencode-go', 'account-a')
                self.assertEqual(fetch_mock.call_count, 1)
                release.set()
                deadline = time.monotonic() + 2
                while service.state('opencode-go', 'account-a') == 'Refreshing models…' and time.monotonic() < deadline:
                    threading.Event().wait(.01)
                service.refresh('opencode-go', 'account-a')
                self.assertEqual(fetch_mock.call_count, 1)
                self.assertIn('cached models retained', service.state('opencode-go', 'account-a'))

    def test_directory_parsers_do_not_guess_missing_limits_or_capabilities(self):
        from fruitfly_agent.providers.connections.methods.opencode_go.catalog import parse_models
        rows = parse_models({'data': [{'id': 'new-model'}]})
        self.assertIsNone(rows[0]['context_window'])
        self.assertFalse(rows[0]['capabilities']['tools'])
        self.assertNotIn('access_token', json.dumps(rows))


    def test_frozen_provider_imports_and_service_resources_load_without_checkout(self):
        import os
        import shutil
        import subprocess
        import sys
        source = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as directory:
            frozen = Path(directory) / 'fruitfly_agent'
            frozen.mkdir()
            shutil.copy2(source / 'fruitfly_agent/__init__.py', frozen)
            for package in ('core', 'providers'):
                shutil.copytree(source / 'fruitfly_agent' / package, frozen / package,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            code = ('import sys; from pathlib import Path; '
                'sys.path.insert(0, sys.argv[1]); '
                'import fruitfly_agent.providers.connections.registry as registry; '
                'assert str(Path(registry.__file__).resolve()).startswith(sys.argv[1]); '
                'definitions=registry.builtin_connections().definitions(); '
                'assert {d.id for d in definitions} == {"opencode-go", "chatgpt"}; '
                'assert all(d.endpoint.startswith("https://") for d in definitions)')
            result = subprocess.run([sys.executable, '-I', '-c', code, str(Path(directory).resolve())],
                cwd=directory, capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)


    def test_explicit_file_storage_is_honored_after_browsing_default_accounts(self):
        from fruitfly_agent.providers.connections.service import ConnectionService
        from fruitfly_agent.providers.auth.stores import FileCredentialStore
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service = ConnectionService(directory=root / 'auth', cache_directory=root / 'cache')
            default = FileCredentialStore(root / 'default')
            with patch('fruitfly_agent.providers.connections.service.configured_store', return_value=default):
                self.assertEqual(service.accounts(), ())
            service.choose_storage('file')
            self.assertEqual(json.loads((root / 'auth/storage.json').read_text()), {'backend': 'file'})
            self.assertEqual(service.credentials().directory, root / 'auth/accounts')
