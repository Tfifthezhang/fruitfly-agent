"""Per-trial host authorization and private inference listener lifecycle."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
import os
import json
import ssl
import tempfile
import time
from typing import Any, AsyncIterator

import httpx

from fruitfly_agent.providers.registry import load_model_specs
from fruitfly_agent.providers.connections.runtime import model_authorization
from fruitfly_agent.providers.connections.registry import builtin_connections
from fruitfly_agent.providers.gateway import ModelRelay, RelayGrant, RelaySocket, RelayRejected
from fruitfly_agent.providers.services import service_definition

TARGET = '/opt/fruitfly-model-relay'


@asynccontextmanager
async def task_access(models: Path, directory: Path, settings: dict[str, Any]) -> AsyncIterator[dict[str, Any] | None]:
    specs = {name: spec for name, spec in load_model_specs(models).items() if spec.access}
    receipt = models.parent / 'runtime.json'
    if receipt.is_file():
        active = json.loads(receipt.read_text(encoding='utf-8'))['connected_models']
        specs = {name: spec for name, spec in specs.items() if name in active}
    if not specs:
        yield None
        return
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='trial-', dir=directory) as temporary:
        root = Path(temporary)
        socket = root / 'model.sock'
        tls = None
        listen = None
        network_url = settings.get('network_url')
        if network_url:
            tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            tls.load_cert_chain(settings['certificate'], settings['private_key'])
            listen = (settings['listen_host'], 0)
        async with httpx.AsyncClient(timeout=httpx.Timeout(600, connect=10)) as upstream:
            relay = ModelRelay(upstream)
            grants = []
            try:
                async with RelaySocket(socket, relay, listen=listen, tls=tls) as listener:
                    if not settings:
                        # The host owns permissions; the container bind stays read-only.
                        # Only this trial sees the socket. Bearer grants are delivered
                        # separately in an owner-only descriptor, never in this mount.
                        directory.chmod(0o711)
                        root.chmod(0o711)
                        socket.chmod(0o666)
                    if network_url:
                        from urllib.parse import urlsplit, urlunsplit
                        parsed = urlsplit(network_url)
                        hostname = parsed.hostname or ''
                        if ':' in hostname:
                            hostname = '[' + hostname + ']'
                        network_url = urlunsplit(('https', hostname + ':' + str(listener.port), '', '', ''))
                    entries = {}
                    for name, spec in specs.items():
                        assert spec.access is not None
                        auth = model_authorization(spec, os.environ)
                        definition = builtin_connections().get(spec.access['integration'])
                        policy = definition.request_policy
                        def headers(session, policy=policy):
                            return policy.prepare({}, session).get('extra_headers', {})
                        route = '/responses' if spec.provider.protocol == 'responses' else '/chat/completions'
                        def validate(request, spec=spec, definition=definition):
                            if definition.output_enforced:
                                field = ('max_output_tokens' if spec.provider.protocol == 'responses' else
                                    service_definition(spec.service, spec.provider.protocol).chat_token_field)
                                limit = request.get(field)
                                if type(limit) is not int or not 0 < limit <= spec.max_output_tokens:
                                    raise RelayRejected('Model output limit exceeds task access')
                        grant = relay.issue(RelayGrant(spec.model, spec.provider.base_url or '', route,
                            auth, time.monotonic() + 86400, prepare_headers=headers, validate_request=validate))
                        grants.append(grant)
                        entries[name] = {'spec': spec.to_dict(), 'authorization': {
                            'integration': auth.integration, 'account': auth.account,
                            'identity': auth.identity, 'label': auth.label},
                            'socket': TARGET + '/' + root.name + '/model.sock', 'grant': grant,
                            'network_url': network_url, 'ca': None}
                    yield {'models': entries}
            finally:
                for grant in grants:
                    relay.revoke(grant)
