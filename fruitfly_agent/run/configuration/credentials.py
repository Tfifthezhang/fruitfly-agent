"""Shared secret draft for configuration forms; values never enter views."""
from pathlib import Path
import re

from fruitfly_agent.providers.config import load_env
from fruitfly_agent.providers.workspace import WorkspacePaths


class CredentialDraft:
    def __init__(self, workspace: Path, environment: dict[str, str]):
        self.workspace = workspace
        self.environment = environment
        self.values: dict[str, str] = {}

    def available(self, name: str) -> bool:
        return bool(self.values.get(name) or self.environment.get(name))

    def check(self, name: str, value: str) -> None:
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name):
            raise ValueError('Credential variable name is invalid')
        if value and (value != value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in value)):
            raise ValueError('Credential must have no surrounding whitespace or control characters')
        if not value and not self.available(name):
            raise ValueError('Credential is missing; enter a value or use an existing secret variable')
        if value and self.environment.get(name) and self.environment[name] != value:
            raise ValueError('Credential variable is already set; use another variable or keep its existing value')
        if value and self.values.get(name) and self.values[name] != value:
            raise ValueError('Credential variable already has another staged value')

    def payloads(self) -> dict[Path, str]:
        if not self.values:
            return {}
        path = WorkspacePaths(self.workspace).secret_file()
        if path.is_symlink():
            raise ValueError('Refusing to write credentials through a symlink')
        text = path.read_text(encoding='utf-8') if path.is_file() else ''
        existing = load_env(path)
        if any(existing.get(key) and existing[key] != value for key, value in self.values.items()):
            raise ValueError('Credential file already has a different value; reload or choose another variable')
        lines = [line for line in text.splitlines(keepends=True)
                 if line.strip().partition('=')[0].strip() not in self.values]
        prefix = ''.join(lines)
        return {path: prefix + ('\n' if prefix and not prefix.endswith('\n') else '') +
                ''.join(f'{key}={value}\n' for key, value in self.values.items())}
