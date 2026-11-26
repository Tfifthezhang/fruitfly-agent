"""Strict owner configuration for an isolated official WorkBuddy runner."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import tomllib
from typing import Any

import yaml
from fruitfly_agent.core.configuration_resources import UniqueLoader
from fruitfly_eval.harbor.host import fields, path_at
from fruitfly_eval.harbor.material import digest, tree_identity
from .tasks import validate_tree

RUNNER_HARBOR_VERSION = '0.23.0'
RUNNER_RESOURCES = ('pyproject.toml', 'uv.lock', 'src/workbuddy_bench', 'configs/bench')


def runner_identity(checkout: Path) -> dict[str, Any]:
    """Hash only declared runtime inputs; never include the checkout's .env or results."""
    if checkout.is_symlink() or not checkout.is_dir():
        raise ValueError('runner checkout must be a real directory')
    rows = []
    for relative in RUNNER_RESOURCES:
        path = checkout / relative
        if not path.exists() or not path.resolve().is_relative_to(checkout.resolve()):
            raise ValueError('runner resource is missing or external: ' + relative)
        if path.is_dir():
            validate_tree(path)
        elif path.is_symlink():
            raise ValueError('runner file resources must not be symlinks')
        rows.append({'path': relative, 'sha256': tree_identity(path, exclude_bytecode=True)})
    project = tomllib.loads((checkout / 'pyproject.toml').read_text())
    harbor = project.get('tool', {}).get('uv', {}).get('sources', {}).get('harbor', {})
    return {'source_sha256': digest(rows), 'files': rows, 'upstream_harbor': harbor,
            'harbor': RUNNER_HARBOR_VERSION}


@dataclass(frozen=True)
class RunnerSettings:
    path: Path
    checkout: Path
    python: Path
    source_sha256: str

    @classmethod
    def read(cls, path: Path) -> RunnerSettings:
        path = path.absolute()
        try:
            value = yaml.load(path.read_text(), Loader=UniqueLoader)
        except yaml.YAMLError:
            raise ValueError('invalid runner configuration YAML') from None
        row = fields(value, {'checkout', 'python', 'source_sha256'}, 'WorkBuddy runner')
        if set(row) != {'checkout', 'python', 'source_sha256'}:
            raise ValueError('runner needs checkout, python and pinned source_sha256')
        checksum = row['source_sha256']
        if not isinstance(checksum, str) or not re.fullmatch(r'[0-9a-f]{64}', checksum):
            raise ValueError('runner source_sha256 must be 64 hexadecimal digits')
        return cls(path, path_at(row['checkout'], path.parent), path_at(row['python'], path.parent), checksum)

    def validate(self) -> dict[str, Any]:
        if not self.python.is_file():
            raise ValueError('runner Python is missing; prepare a separate WorkBuddy environment')
        identity = runner_identity(self.checkout)
        if identity['source_sha256'] != self.source_sha256:
            raise ValueError('runner source differs from pinned source_sha256')
        return identity

    def to_dict(self) -> dict[str, str]:
        return {'checkout': str(self.checkout), 'python': str(self.python),
                'source_sha256': self.source_sha256}
