"""One inventory for installation validation, content identity and frozen resources."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from email.parser import Parser
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import stat
import tomllib
from typing import Any, Iterator
import zipfile
from fruitfly_agent.runtime_spec.resources import (safe_resource_path as _safe_path,
    excluded_resource as _excluded, validate_resource_file as _source_file, declared_resource_files)


SOURCE_FILES = ("pyproject.toml", "README.md", "LICENSE", "THIRD_PARTY_NOTICES.md")
SOURCE_PACKAGES = ("fruitfly_agent", "fruitfly_eval")
INSTALLATION_SCHEMA = 2











def _source_files(root: Path, project: dict[str, Any]) -> tuple[str, ...]:
    selected = set(SOURCE_FILES)
    for package in SOURCE_PACKAGES:
        for path in (root / package).rglob('*.py'):
            name = path.relative_to(root).as_posix()
            if not _excluded(PurePosixPath(name)):
                selected.add(name)
    data = project.get('tool', {}).get('setuptools', {}).get('package-data', {})
    selected.update(declared_resource_files(root, data, SOURCE_PACKAGES))
    for name in selected:
        _source_file(root, name)
    return tuple(sorted(selected))


def _wheel_files(path: Path) -> tuple[dict[str, Any], tuple[str, ...]]:
    with zipfile.ZipFile(path) as archive:
        entries = [entry for entry in archive.infolist() if not entry.is_dir()]
        names = {entry.filename for entry in entries}
        if len(names) != len(entries):
            raise ValueError('wheel contains duplicate file names')
        metadata = [name for name in names if name.endswith('.dist-info/METADATA')]
        if len(metadata) != 1 or any(f'{name}/__init__.py' not in names for name in SOURCE_PACKAGES):
            raise ValueError('wheel must contain FruitFlyAgent runtime, Eval, and one metadata record')
        fields = Parser().parsestr(archive.read(metadata[0]).decode('utf-8'))
        dist_info = metadata[0].split('/')[0]
        record = dist_info + '/RECORD'
        if record in names:
            for row in csv.reader(io.StringIO(archive.read(record).decode('utf-8'))):
                if row and row[0] not in names:
                    raise ValueError('wheel is missing a recorded file: ' + row[0])
        selected = []
        for entry in entries:
            relative = _safe_path(entry.filename)
            if stat.S_ISLNK(entry.external_attr >> 16):
                raise ValueError('wheel cannot contain symlinks: ' + entry.filename)
            if relative.parts[0] in SOURCE_PACKAGES:
                if _excluded(relative):
                    raise ValueError('wheel contains excluded local state: ' + entry.filename)
                selected.append(entry.filename)
            elif relative.parts[:2] == (dist_info, 'licenses') and len(relative.parts) > 2:
                selected.append(entry.filename)
        return {'name': fields['Name'], 'version': fields['Version']}, tuple(sorted(selected))


def _destination(name: str) -> str:
    path = PurePosixPath(name)
    if path.parts[0].endswith('.dist-info'):
        return str(PurePosixPath('licenses', *path.parts[2:]))
    return name


@dataclass(frozen=True)
class InstallationMaterial:
    path: Path
    files: tuple[str, ...]

    def _contents(self) -> Iterator[tuple[str, bytes]]:
        if self.path.is_file():
            with zipfile.ZipFile(self.path) as archive:
                for name in self.files:
                    yield _destination(name), archive.read(name)
        else:
            for name in self.files:
                _source_file(self.path, name)
                yield name, (self.path / name).read_bytes()

    def identity(self, *, destination: Path | None = None) -> dict[str, Any]:
        """Hash the exact bytes copied, with an additional identity for a wheel archive."""
        rows = []
        for name, contents in self._contents():
            rows.append((name, hashlib.sha256(contents).hexdigest()))
            if destination is not None:
                target = destination / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(contents)
        rows.sort()
        result = {'schema_version': INSTALLATION_SCHEMA, 'project': 'fruitfly-agent', 'version': '0.1',
                  'kind': 'wheel' if self.path.is_file() else 'source',
                  'sha256': hashlib.sha256(json.dumps(rows, separators=(',', ':')).encode()).hexdigest(),
                  'files': rows}
        if self.path.is_file():
            result['archive_sha256'] = hashlib.sha256(self.path.read_bytes()).hexdigest()
        return result

    def snapshot(self, destination: Path) -> dict[str, Any]:
        destination.mkdir(parents=True)
        identity = self.identity(destination=destination)
        if identity != installation_identity(self.path):
            raise ValueError('installation material changed while freezing; run eval prepare again')
        return identity


def installation_material(path: Path) -> InstallationMaterial:
    """Inspect declared source resources or actual wheel contents, excluding workspace state."""
    path = path.expanduser().resolve()
    if path.is_dir():
        for name in (*SOURCE_FILES, *(f'{name}/__init__.py' for name in SOURCE_PACKAGES)):
            _source_file(path, name)
        document = tomllib.loads((path / 'pyproject.toml').read_text(encoding='utf-8'))
        project = document.get('project', {})
        files = _source_files(path, document)
    elif path.is_file() and path.suffix == '.whl':
        try:
            project, files = _wheel_files(path)
        except zipfile.BadZipFile as exc:
            raise ValueError('invalid FruitFlyAgent wheel') from exc
    else:
        raise ValueError('FRUITFLY_EVAL_PACKAGE must point to a source directory or .whl file')
    if project.get('name') != 'fruitfly-agent' or project.get('version') != '0.1':
        raise ValueError('installation material must be fruitfly-agent version 0.1')
    return InstallationMaterial(path, files)


def installation_identity(path: Path) -> dict[str, Any]:
    return installation_material(path).identity()


def validate_installation(path: Path) -> Path:
    return installation_material(path).path


def resolve_installation(value: str | None, *, checkout: Path) -> Path:
    if value and value.strip():
        return validate_installation(Path(value))
    try:
        return validate_installation(checkout)
    except ValueError as exc:
        raise ValueError(
            'no complete source checkout; set FRUITFLY_EVAL_PACKAGE to an explicit '
            'FruitFlyAgent source directory or wheel'
        ) from exc
