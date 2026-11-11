"""Strict local document reading with explicit references and source receipts."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any

from fruitfly_agent.core.configuration_resources import (decode_yaml, parameter_value, YamlSyntaxError,
    package_bytes as _package_bytes, validate_default_resource)


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


def package_document(package, resource):
    """Read only a package selected by trusted owner registration, never YAML imports."""
    data = _package_bytes(package, resource)
    try:
        value = decode_yaml(data)
    except YamlSyntaxError as exc:
        raise ValueError('invalid registered component resource') from exc
    return value, PackageDocumentSource(package, resource, hashlib.sha256(data).hexdigest())


def parameter_default(package, resource, path):
    """Derive typed constructor defaults from the owner's single parameter document."""
    return parameter_value(package_document(package, resource)[0], path)


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
            return decode_yaml(data)
        except YamlSyntaxError as exc:
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
