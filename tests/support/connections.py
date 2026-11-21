"""Isolated account stores and normalized model directory fixtures."""
from pathlib import Path
import time
from fruitfly_agent.providers.auth.stores import FileCredentialStore
from fruitfly_agent.providers.connections.catalog import CatalogSnapshot
from fruitfly_agent.providers.connections.service import ConnectionService
from fruitfly_agent.providers.registry import default_registry

def connection_service(root):
    root = Path(root)
    store = FileCredentialStore(root / 'accounts')
    service = ConnectionService(directory=root / 'auth', cache_directory=root / 'cache', store=store)
    return service

def account_record(account='account-a', integration='chatgpt', **changes):
    return {'account': account, 'integration': integration, 'status': 'connected', 'label': 'Offline account',
        'access_token': 'offline-token-a', 'refresh_token': 'offline-refresh',
        'binding': 'stable-account-binding', 'binding_secret': 'offline-binding',
        'subject': 'subject-a', 'client_id': 'client-a', 'expires_at': time.time() + 3600, **changes}

def seed_directory(service, integration='opencode-go', account='account-a', *, count=1, fetched_at=None):
    models = tuple({'id': f'model-{i}', 'name': f'Model {i}', 'context_window': 8192,
        'max_output_tokens': 2048, 'capabilities': {'tools': True, 'streaming': True,
            'reasoning': False, 'vision': False, 'parallel_tool_calls': False}} for i in range(count))
    snapshot = CatalogSnapshot(models, fetched_at if fetched_at is not None else time.time(), 'revision-a')
    service.cache.write(service.scope(integration, account), snapshot, complete=True)
    return snapshot
