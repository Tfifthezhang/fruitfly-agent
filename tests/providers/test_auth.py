"""Authorization validation, secret isolation and renewal use fake remote services."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.parse import urlencode
from fruitfly_agent.providers.auth.stores import FileCredentialStore
from fruitfly_agent.providers.auth.session import AuthSession
from fruitfly_agent.providers.auth.oauth import OAuthAttempt
from fruitfly_agent.providers.connections.methods.chatgpt.auth import authorization_url, complete, refresh
from fruitfly_agent.core.errors import FatalError
from tests.support.connections import account_record

class AuthTests(unittest.TestCase):
    def test_environment_binding_survives_restart_and_changes_with_key(self):
        from fruitfly_agent.providers.auth.environment import EnvironmentAuthorization
        from tests.support.connections import connection_service

        with tempfile.TemporaryDirectory() as directory:
            service = connection_service(directory)
            environment = {'GO_KEY': 'fixture-a'}
            binding_directory = service.directory / 'bindings'
            first = EnvironmentAuthorization('opencode-go', 'GO_KEY', environment,
                                             binding_directory=binding_directory)
            restarted = EnvironmentAuthorization('opencode-go', 'GO_KEY', environment,
                                                 binding_directory=binding_directory)
            self.assertEqual(first.identity, restarted.identity)
            self.assertEqual(first.identity, service.bind_variable('opencode-go', 'GO_KEY', environment))
            changed = EnvironmentAuthorization('opencode-go', 'GO_KEY', {'GO_KEY': 'fixture-b'},
                                               binding_directory=binding_directory)
            self.assertNotEqual(first.identity, changed.identity)
            self.assertNotIn('fixture-a', first.identity)

    def test_private_files_atomic_updates_and_symlink_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            store = FileCredentialStore(Path(directory) / 'accounts')
            store.modify('account-a', lambda _: account_record())
            path = store._path('account-a')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertNotIn('offline-token', repr(store.list()))
            with self.assertRaises(RuntimeError):
                store.modify('account-a', lambda _: (_ for _ in ()).throw(RuntimeError()))
            self.assertEqual(store.read('account-a')['access_token'], 'offline-token-a')
            path.chmod(0o644)
            with self.assertRaisesRegex(ValueError, 'permissions'):
                store.read('account-a')
            path.unlink()
            target = Path(directory) / 'outside'
            target.write_text('private')
            path.symlink_to(target)
            with self.assertRaises(OSError):
                store.read('account-a')

    def test_refresh_is_serialized_and_account_identity_is_stable(self):
        with tempfile.TemporaryDirectory() as directory:
            store = FileCredentialStore(Path(directory) / 'accounts')
            store.modify('account-a', lambda _: account_record(expires_at=0))
            updates = []
            def renew(record):
                updates.append(record['refresh_token'])
                return {**record, 'access_token': 'offline-token-b', 'refresh_token': 'replacement', 'expires_at': time.time() + 3600}
            sessions = [AuthSession(store, 'account-a', 'chatgpt', renew) for _ in range(8)]
            with ThreadPoolExecutor(max_workers=8) as workers:
                values = list(workers.map(lambda s: s.resolve(), sessions))
            self.assertEqual(values, ['offline-token-b'] * 8)
            self.assertEqual(updates, ['offline-refresh'])
            self.assertEqual({s.identity for s in sessions}, {'stable-account-binding'})
            store.modify('account-a', lambda r: {**r, 'binding': 'other-account'})
            with self.assertRaises(FatalError):
                sessions[0].resolve()

    def test_callback_state_client_path_and_denial(self):
        with patch('fruitfly_agent.providers.auth.oauth.HTTPServer.__init__', return_value=None), patch(
                'fruitfly_agent.providers.auth.oauth.HTTPServer.serve_forever'), patch(
                'fruitfly_agent.providers.auth.oauth.HTTPServer.shutdown'), patch(
                'fruitfly_agent.providers.auth.oauth.HTTPServer.server_close'), patch(
                'fruitfly_agent.providers.auth.oauth.HTTPServer.server_port', 1455, create=True):
            attempt = OAuthAttempt(client_id='client-a')
            try:
                url = authorization_url(attempt, 'urn:uuid:offline', account_record(id_token='hint'))
                self.assertIn('client_id=client-a', url)
                self.assertNotIn('agent_name_hint', url)
                for query in ({'state': 'wrong', 'code': 'x'}, {'state': attempt.state, 'code': 'x', 'client_id': 'other'}):
                    with self.assertRaises(ValueError):
                        attempt.accept(attempt.redirect_uri + '?' + urlencode(query))
                with self.assertRaises(ValueError):
                    attempt.accept('http://127.0.0.1:1455/wrong?' + urlencode({'state': attempt.state, 'code': 'x'}))
                attempt.accept(attempt.redirect_uri + '?' + urlencode({'state': attempt.state, 'error': 'access_denied'}))
                self.assertTrue(attempt.finished.is_set())
                self.assertIsNone(attempt.result)
            finally:
                attempt.close()
                attempt.close()

    def test_exchange_rejects_identity_mismatch_and_missing_plan_permission(self):
        token = dict(access_token='a', refresh_token='b', id_token='c', expires_in=3600, scope='openid')
        attempt = type('Attempt', (), {'result': {'client_id': 'client-a', 'code': 'code'}, 'error': '',
            'verifier': 'verifier', 'redirect_uri': 'http://127.0.0.1:1455/auth/callback', 'nonce': 'nonce'})()
        with patch('fruitfly_agent.providers.connections.methods.chatgpt.auth.token_request', return_value=token), patch(
                'fruitfly_agent.providers.connections.methods.chatgpt.auth.claims', return_value={'sub': 'other'}):
            with self.assertRaises(ValueError):
                complete(attempt, account_record())
        with patch('fruitfly_agent.providers.connections.methods.chatgpt.auth.token_request', return_value=token), patch(
                'fruitfly_agent.providers.connections.methods.chatgpt.auth.claims', return_value={'sub': 'subject-a'}):
            result = complete(attempt, account_record())
            self.assertEqual(result['status'], 'plan_disabled')
            with self.assertRaises(FatalError):
                refresh(account_record())

    def test_id_token_signature_audience_and_nonce_are_validated(self):
        import jwt
        from cryptography.hazmat.primitives.asymmetric import rsa
        from fruitfly_agent.providers.connections.methods.chatgpt.auth import claims
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        jwk = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
        jwk['kid'] = 'test-key'
        token = jwt.encode({'iss': 'https://auth.openai.com', 'aud': 'client-a', 'sub': 'subject-a',
            'exp': time.time() + 120, 'iat': time.time(), 'nonce': 'nonce-a'}, key, algorithm='RS256', headers={'kid': 'test-key'})
        def get(url, **kwargs):
            value = {'jwks_uri': 'https://auth.openai.com/keys'} if 'well-known' in url else {'keys': [jwk]}
            return type('Reply', (), {'json': lambda self: value})()
        with patch('httpx.get', side_effect=get):
            self.assertEqual(claims(token, 'client-a', 'nonce-a')['sub'], 'subject-a')
            for audience, nonce in (('client-b', 'nonce-a'), ('client-a', 'wrong')):
                with self.assertRaises(ValueError):
                    claims(token, audience, nonce)


    def test_invalid_refresh_clears_unusable_tokens_but_transient_failure_preserves_them(self):
        with tempfile.TemporaryDirectory() as directory:
            store = FileCredentialStore(Path(directory) / 'accounts')
            def fail(record):
                raise FatalError('offline', details={'kind': 'authentication_unavailable'})
            store.modify('account-a', lambda _: account_record(expires_at=0))
            session = AuthSession(store, 'account-a', 'chatgpt', fail)
            with self.assertRaises(FatalError):
                session.resolve()
            self.assertIn('refresh_token', store.read('account-a'))
            def invalid(record):
                raise FatalError('offline', details={'kind': 'authentication_required'})
            session.refresh = invalid
            with self.assertRaises(FatalError):
                session.resolve()
            value = store.read('account-a')
            self.assertEqual(value['status'], 'authorization_required')
            self.assertNotIn('refresh_token', value)
            self.assertNotIn('access_token', value)
            self.assertEqual(value['client_id'], 'client-a')
