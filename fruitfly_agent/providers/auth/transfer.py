"""Transfer one explicitly selected registration over an authenticated channel."""
from __future__ import annotations

import json
import math
import re
import shlex
import subprocess
from typing import Any, BinaryIO, Collection

from .contracts import CredentialStore

_MAX_BYTES = 128 * 1024
_FIELDS = frozenset({'account', 'integration', 'status', 'label', 'access_token',
    'refresh_token', 'id_token', 'binding', 'binding_secret', 'subject', 'client_id',
    'expires_at', 'scope', 'scopes', 'account_id', 'plan_type'})


def registration(store: CredentialStore, account: str) -> bytes:
    """Read only the selected registration, without triggering renewal."""
    value = store.read(account)
    if not value or value.get('account') != account or value.get('status') != 'connected':
        raise ValueError('Select a connected account registration')
    if value.keys() - _FIELDS:
        raise ValueError('Account registration contains unsupported transfer fields')
    payload = json.dumps({'registration': value}, allow_nan=False).encode()
    if len(payload) > _MAX_BYTES:
        raise ValueError('Account registration exceeds the transfer limit')
    return payload


def receive(source: BinaryIO, store: CredentialStore, *, integrations: Collection[str], replace: bool = False) -> str:
    """Atomically publish one registration; preserve every other local record."""
    raw = source.read(_MAX_BYTES + 1)
    if len(raw) > _MAX_BYTES:
        raise ValueError('Account registration exceeds the transfer limit')
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeError):
        raise ValueError('Invalid account transfer') from None
    if not isinstance(payload, dict) or set(payload) != {'registration'}:
        raise ValueError('Invalid account transfer')
    value = payload['registration']
    if not isinstance(value, dict) or value.keys() - _FIELDS:
        raise ValueError('Invalid account registration fields')
    required = ('account', 'integration', 'binding', 'binding_secret', 'access_token')
    if (any(not isinstance(value.get(key), str) or not value[key] for key in required)
            or value.get('status') != 'connected'
            or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', value['account'])):
        raise ValueError('Invalid connected account registration')
    if value['integration'] not in integrations:
        raise ValueError('Unsupported account integration')
    if 'expires_at' in value and (type(value['expires_at']) not in (int, float)
            or not math.isfinite(value['expires_at'])):
        raise ValueError('Invalid account expiration')
    account = value['account']
    def update(current: dict[str, Any] | None) -> dict[str, Any]:
        if current is not None and not replace:
            raise ValueError('Account already exists; explicitly replace this registration')
        if current is not None and current.get('integration') != value['integration']:
            raise ValueError('Cannot replace a different account integration')
        return value
    store.modify(account, update)
    return str(account)


def deploy(store: CredentialStore, account: str, host: str, *, python: str = 'python3',
           replace: bool = False) -> None:
    """Send secrets on SSH stdin, never in arguments, output, or temporary files."""
    if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.@-]*', host):
        raise ValueError('Use an SSH host alias or user@host')
    if not python or '\x00' in python:
        raise ValueError('Invalid remote Python executable')
    command = [python, '-m', 'fruitfly_agent.providers.auth', 'receive']
    if replace:
        command.append('--replace')
    payload = registration(store, account)
    try:
        result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '--', host, shlex.join(command)],
            input=payload, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError('SSH account deployment failed or timed out') from None
    if result.returncode:
        # Remote stderr may contain tokens or server banners. Never propagate it.
        raise ValueError('SSH account deployment failed; check host access and remote credential storage')
