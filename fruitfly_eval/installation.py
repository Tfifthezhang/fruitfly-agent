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


SOURCE_FILES = ("pyproject.toml", "README.md", "LICENSE", "THIRD_PARTY_NOTICES.md")
SOURCE_PACKAGES = ("fruitfly_agent", "fruitfly_eval")
INSTALLATION_SCHEMA = 2


def _safe_path(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if not name or not path.parts or path.is_absolute() or '..' in path.parts or '\\' in name or str(path) != name:
        raise ValueError('installation file must have a canonical relative path: ' + name)
    return path


def _excluded(path: PurePosixPath) -> bool:
    return (any(part.startswith('.') or part == '__pycache__' for part in path.parts)
            or path.suffix in {'.pyc', '.pyo'} or path.name == 'secrets.env'
            or (path.name == 'models.yaml' and
                path.as_posix() != 'fruitfly_agent/run/configuration/templates/models.yaml'))


def _source_file(root: Path, name: str) -> None:
    relative = _safe_path(name)
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError('installation material cannot contain symlinks: ' + name)
    if not current.is_file():
        raise ValueError('incomplete FruitFlyAgent source: ' + name)


def _source_files(root: Path, project: dict[str, Any]) -> tuple[str, ...]:
    selected = set(SOURCE_FILES)
    for package in SOURCE_PACKAGES:
        for path in (root / package).rglob('*.py'):
            name = path.relative_to(root).as_posix()
            if not _excluded(PurePosixPath(name)):
                selected.add(name)
    data = project.get('tool', {}).get('setuptools', {}).get('package-data', {})
    if not isinstance(data, dict):
        raise ValueError('package-data must declare package resource patterns')
    for package, patterns in data.items():
        if not isinstance(patterns, list) or not patterns or any(not isinstance(p, str) for p in patterns):
            raise ValueError('package-data requires nonempty resource pattern lists')
        if package == '*':
            directories = tuple(path.parent for name in SOURCE_PACKAGES
                                for path in (root / name).rglob('__init__.py')
                                if not _excluded(PurePosixPath(path.relative_to(root).as_posix())))
        else:
            if (not re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*', package)
                    or package.split('.')[0] not in SOURCE_PACKAGES):
                raise ValueError('package-data must belong to FruitFlyAgent or Eval')
            directories = (root.joinpath(*package.split('.')),)
        for pattern in patterns:
            _safe_path(pattern)
            matched = []
            for directory in directories:
                for path in directory.glob(pattern):
                    if not path.is_file() and not path.is_symlink():
                        continue
                    name = path.relative_to(root).as_posix()
                    if _excluded(PurePosixPath(name)):
                        raise ValueError('package resource selects excluded local state: ' + name)
                    matched.append(name)
            if not matched and not any(character in pattern for character in '*?['):
                raise ValueError(f'missing declared package resource: {package}/{pattern}')
            selected.update(matched)
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
