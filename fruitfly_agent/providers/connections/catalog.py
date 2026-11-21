"""Explicit model-directory caching; reading never performs network requests."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any


@dataclass(frozen=True)
class CatalogScope:
    integration: str
    endpoint: str
    account: str
    region: str = ''

    def key(self) -> str:
        return hashlib.sha256(json.dumps(
            [self.integration, self.endpoint, self.account, self.region],
            separators=(',', ':')).encode()).hexdigest()


@dataclass(frozen=True)
class CatalogSnapshot:
    """A historical directory observation, never a live entitlement guarantee."""
    models: tuple[dict[str, Any], ...]
    fetched_at: float
    etag: str = ''
    last_modified: str = ''

    def stale(self, now: float, *, ttl: float = 86400) -> bool:
        return now < self.fetched_at or now - self.fetched_at >= ttl


class CatalogCache:
    """Atomic, account-scoped cache. Callers own fetches and retry scheduling."""

    def __init__(self, directory: Path):
        self.directory = directory

    def read(self, scope: CatalogScope) -> CatalogSnapshot | None:
        try:
            value = json.loads((self.directory / (scope.key() + '.json')).read_text())
            if not isinstance(value, dict) or value.get('schema_version') != 1:
                return None
            return self._snapshot(value)
        except (OSError, ValueError, TypeError, KeyError):
            return None

    @staticmethod
    def _snapshot(value: dict[str, Any]) -> CatalogSnapshot:
        if not isinstance(value, dict):
            raise ValueError('invalid model directory cache')
        models = value['models']
        if not isinstance(models, list) or any(not isinstance(m, dict)
                or not isinstance(m.get('id'), str) or not m['id'] for m in models):
            raise ValueError('invalid model directory')
        if len({m['id'] for m in models}) != len(models):
            raise ValueError('duplicate model IDs')
        import math
        timestamp = value['fetched_at']
        if isinstance(timestamp, bool) or not isinstance(timestamp, (float, int)) or not math.isfinite(timestamp) or timestamp < 0:
            raise ValueError('invalid directory timestamp')
        if any(not isinstance(value.get(k, ''), str) for k in ('etag', 'last_modified')):
            raise ValueError('invalid conditional request metadata')
        # Only normalized non-secret descriptors enter persistent cache records.
        allowed = {'id', 'name', 'context_window', 'max_output_tokens', 'input_limit', 'capabilities', 'pricing', 'options'}
        if any(set(row) - allowed for row in models):
            raise ValueError('Model directory contains undeclared fields')
        for row in models:
            options = row.get('options', {})
            if not isinstance(options, dict) or any(not isinstance(key, str) or not isinstance(choices, list)
                    or any(not isinstance(choice, str) or not choice for choice in choices)
                    for key, choices in options.items()):
                raise ValueError('Invalid model directory option choices')
        import copy
        return CatalogSnapshot(tuple(copy.deepcopy(models)), timestamp, value.get('etag', ''), value.get('last_modified', ''))

    def write(self, scope: CatalogScope, snapshot: CatalogSnapshot, *, complete: bool) -> None:
        if not complete:
            raise ValueError('incomplete directories cannot replace cached models')
        value = dict(schema_version=1, models=list(snapshot.models), fetched_at=snapshot.fetched_at,
                     etag=snapshot.etag, last_modified=snapshot.last_modified)
        self._snapshot(value)
        data = json.dumps(value, allow_nan=False).encode()
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, name = tempfile.mkstemp(prefix='.catalog-', dir=self.directory)
        try:
            with os.fdopen(descriptor, 'wb') as output:
                output.write(data)
            os.replace(name, self.directory / (scope.key() + '.json'))
        finally:
            Path(name).unlink(missing_ok=True)
