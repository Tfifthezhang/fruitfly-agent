"""Strict YAML data decoding and bounded resources; no owner or execution policy."""
from copy import deepcopy
from functools import lru_cache
from importlib.resources import files
import re
import yaml


class YamlSyntaxError(ValueError):
    """Invalid YAML syntax or text encoding, separate from owner rejection."""


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


def package_bytes(package, resource):
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



@lru_cache(maxsize=64)
def _parsed(data):
    try:
        return yaml.load(data.decode('utf-8'), Loader=UniqueLoader)
    except (yaml.YAMLError, UnicodeError) as exc:
        raise YamlSyntaxError('invalid YAML document') from exc


def decode_yaml(data):
    """Return detached data, rejecting duplicate/non-string mapping keys."""
    return deepcopy(_parsed(data))


def parameter_value(document, path):
    value = document['parameters']
    for part in path.split('.'):
        value = value[part]
    return value


def package_parameter(package, resource, path):
    """Owners explicitly choose installed data; values cannot select imports."""
    return parameter_value(decode_yaml(package_bytes(package, resource)), path)
