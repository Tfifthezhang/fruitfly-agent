"""Retain opaque static-key bindings in an owner-only local store."""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from pathlib import Path

from .stores import FileCredentialStore


def static_key_binding(directory: Path, integration: str, reference: str, key: str) -> str:
    account = hashlib.sha256(json.dumps([integration, reference]).encode()).hexdigest()
    store = FileCredentialStore(directory)

    def update(previous):
        record = dict(previous or {'account': account, 'salt': secrets.token_hex(32)})
        fingerprint = hmac.new(record['salt'].encode(), key.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(record.get('fingerprint', ''), fingerprint):
            record.update(fingerprint=fingerprint, binding=secrets.token_hex(32))
        return record

    return str(store.modify(account, update)['binding'])
