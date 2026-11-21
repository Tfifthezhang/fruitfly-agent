"""Task access material, account isolation and model binding without sockets."""
from contextlib import asynccontextmanager
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, AsyncMock
import yaml

from fruitfly_agent.providers.gateway.access import access_registry
from fruitfly_agent.providers.gateway import ModelRelay, RelayRejected
from fruitfly_agent.providers.specs import ModelSpec
from fruitfly_eval.harbor.model_access import task_access


class ModelAccessTests(unittest.IsolatedAsyncioTestCase):
    async def test_task_grants_are_revoked_and_account_tokens_never_enter_descriptor(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        spec = ModelSpec.from_dict('work', {'sdk': 'openai', 'protocol': 'chat-completions',
            'service': 'opencode-go', 'base_url': 'https://opencode.ai/inference/go/v1',
            'model': 'fixture', 'context_window': 8192,
            'access': {'integration': 'opencode-go', 'account': 'fixture-account'}})
        models = root / 'models.yaml'
        models.write_text(yaml.safe_dump({'models': {'work': spec.to_dict()}}))
        auth = AsyncMock(integration='opencode-go', account='fixture-account', identity='stable-binding', label='Fixture')
        auth.token.return_value = 'never-export-this-upstream-token'
        relays = []
        def relay(client):
            result = ModelRelay(client)
            relays.append(result)
            return result
        @asynccontextmanager
        async def listener(*args, **kwargs):
            yield None
        with patch('fruitfly_eval.harbor.model_access.model_authorization', return_value=auth), patch(
            'fruitfly_eval.harbor.model_access.RelaySocket', listener), patch(
            'fruitfly_eval.harbor.model_access.ModelRelay', side_effect=relay):
            async with task_access(models, root / 'relay', {}) as descriptor:
                encoded = json.dumps(descriptor)
                self.assertNotIn('never-export-this-upstream-token', encoded)
                auth.token.assert_not_called()
                entry = descriptor['models']['work']
                grant = entry['grant']
                self.assertEqual(relays[0]._grant(grant).model, 'fixture')
                with self.assertRaises(RelayRejected):
                    async with relays[0].stream(grant, '/chat/completions', json.dumps({
                        'model': 'fixture', 'stream': True, 'max_tokens': 999999}).encode()):
                        self.fail('Out-of-range output reached upstream')
                auth.token.assert_not_called()
                path = root / 'access.json'
                path.write_text(encoded)
                path.chmod(0o600)
                with patch('fruitfly_agent.providers.auth.stores.configured_store') as store:
                    provider = access_registry(path).create(spec, {})
                    self.assertEqual(provider.auth.identity, 'stable-binding')
                    await provider.close()
                    store.assert_not_called()
                with self.assertRaisesRegex(ValueError, 'outside task access'):
                    access_registry(path).create(ModelSpec.from_dict('other', spec.to_dict()), {})
            with self.assertRaises(RelayRejected):
                relays[0]._grant(grant)
            self.assertEqual(list((root / 'relay').iterdir()), [])

    async def test_access_file_rejects_public_permissions(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        path = root / 'access.json'
        path.write_text('{"models": {}}')
        path.chmod(0o644)
        with self.assertRaisesRegex(ValueError, 'owner-only'):
            access_registry(path)
