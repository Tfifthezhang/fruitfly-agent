"""Explicit subprocess transport for optional execution engines with isolated dependencies."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any


class IsolatedPython:
    def __init__(self, python: Path, module: str, sources: tuple[Path, ...]):
        if not python.is_absolute() or not sources or any(not p.is_absolute() for p in sources):
            raise ValueError('isolated engines require absolute interpreter and source paths')
        self.python, self.module, self.sources = python, module, sources

    def environment(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        values = {**os.environ, **(extra or {}), 'PYTHONPATH': os.pathsep.join(map(str, self.sources)),
                  'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONNOUSERSITE': '1'}
        values.pop('PYTHONHOME', None)
        return values

    def command(self, *arguments: str) -> list[str]:
        return [str(self.python), '-P', '-m', self.module, *arguments]

    def call(self, operation: str, payload: dict[str, Any], *, timeout: float = 60) -> dict[str, Any]:
        # Neither interpreter arguments nor requests are interpolated into shell code.
        with tempfile.TemporaryDirectory(prefix='fruitfly-engine-') as directory:
            root = Path(directory)
            request, response = root / 'request.json', root / 'response.json'
            request.write_text(json.dumps({'operation': operation, 'payload': payload}, allow_nan=False))
            try:
                completed = subprocess.run(self.command('--request', str(request), '--response', str(response)),
                    env=self.environment(), cwd=root, capture_output=True, text=True, timeout=timeout)
            except subprocess.TimeoutExpired as exc:
                raise ValueError('execution engine operation timed out: ' + operation) from exc
            if not response.is_file():
                raise ValueError('execution engine returned no response; ' + completed.stderr[-2000:])
            value = json.loads(response.read_text())
            if not isinstance(value, dict):
                raise ValueError('execution engine response must be an object')
            if completed.returncode or value.get('ok') is not True:
                raise ValueError('execution engine: ' + str(value.get('error', 'failed')))
            result = value.get('result')
            if not isinstance(result, dict):
                raise ValueError('execution engine response must contain an object')
            return result
