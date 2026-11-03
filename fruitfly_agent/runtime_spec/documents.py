"""Strict local document reading with explicit references and source receipts."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from pathlib import Path
from importlib.resources import files
from copy import deepcopy
from functools import lru_cache
from typing import Any

import yaml


class UniqueLoader(yaml.SafeLoader):
    pass


def unique_mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, str) or key in result:
            raise ValueError('configuration keys must be distinct strings')
        result[key] = loader.construct_object(value_node)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def mapping(value, allowed, label):
    if not isinstance(value, dict) or set(value) - set(allowed):
        raise ValueError(label + ' contains unknown fields or is not a mapping')
    return value


@dataclass(frozen=True)
class DocumentSource:
    path: str
    digest: str

    def check(self):
        if hashlib.sha256(Path(self.path).read_bytes()).hexdigest() != self.digest:
            raise ValueError('configuration source changed: ' + self.path)


@dataclass(frozen=True)
class PackageDocumentSource:
    """Receipt for an explicitly registered, installed component resource."""
    package: str
    resource: str
    digest: str

    @property
    def path(self):
        return 'package:' + self.package + '/' + self.resource

    def check(self):
        if hashlib.sha256(_package_bytes(self.package, self.resource)).hexdigest() != self.digest:
            raise ValueError('configuration source changed: ' + self.path)


def _package_bytes(package, resource):
    validate_default_resource((package, resource))
    with files(package).joinpath(resource).open('rb') as stream:
        data = stream.read(2_000_001)
    if len(data) > 2_000_000:
        raise ValueError('configuration document exceeds 2 MB')
    return data


def validate_default_resource(value):
    if (not isinstance(value, tuple) or len(value) != 2
            or not isinstance(value[0], str) or not re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*', value[0])
            or not isinstance(value[1], str) or value[1].startswith('.')
            or '/' in value[1] or '\\' in value[1] or not value[1].endswith('.yaml')):
        raise ValueError('registered defaults require a package and one YAML resource name')


def package_document(package, resource):
    """Read only a package selected by trusted owner registration, never YAML imports."""
    data = _package_bytes(package, resource)
    value = deepcopy(_parse_package(data))
    return value, PackageDocumentSource(package, resource, hashlib.sha256(data).hexdigest())


@lru_cache(maxsize=64)
def _parse_package(data):
    try:
        return yaml.load(data.decode('utf-8'), Loader=UniqueLoader)
    except (yaml.YAMLError, UnicodeError) as exc:
        raise ValueError('invalid registered component resource') from exc


def parameter_default(package, resource, path):
    """Derive typed constructor defaults from the owner's single parameter document."""
    value = package_document(package, resource)[0]['parameters']
    for part in path.split('.'):
        value = value[part]
    return value


class DocumentReader:
    """Read explicit file/inline references; no environment or template execution."""
    def __init__(self):
        self.sources: dict[str, DocumentSource] = {}
        self.active: set[Path] = set()

    def read(self, path: str | Path) -> Any:
        target = Path(path).resolve()
        if target in self.active:
            raise ValueError('cyclic configuration reference: ' + str(target))
        data = target.read_bytes()
        if len(data) > 2_000_000:
            raise ValueError('configuration document exceeds 2 MB: ' + str(target))
        self.sources[str(target)] = DocumentSource(str(target), hashlib.sha256(data).hexdigest())
        try:
            return yaml.load(data.decode('utf-8'), Loader=UniqueLoader)
        except (yaml.YAMLError, UnicodeError) as exc:
            raise ValueError('invalid configuration document: ' + str(target)) from exc

    def reference(self, value, declaring: Path):
        mapping(value, {'file', 'inline'}, 'document reference')
        if len(value) != 1:
            raise ValueError('document reference needs exactly one file or inline')
        if 'inline' in value:
            return value['inline'], declaring
        name = value['file']
        if not isinstance(name, str) or not name.strip():
            raise ValueError('document file reference must be a nonempty string')
        target = Path(name).expanduser()
        target = (target if target.is_absolute() else declaring.parent / target).resolve()
        return self.read(target), target
