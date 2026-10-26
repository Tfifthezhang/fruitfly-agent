"""Strict local document reading with explicit references and source receipts."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
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
