"""Resolve one shared baseline without silently overriding explicit selections."""
from pathlib import Path


def runtime_reference(workspace, config_path=None, profile=None, *, inherited_path=None, inherited_profile=None):
    workspace = Path(workspace)
    def path(value):
        item = Path(value).expanduser()
        return (item if item.is_absolute() else workspace / item).resolve()
    if config_path and inherited_path and path(config_path) != path(inherited_path):
        raise ValueError('explicit runtime configurations differ between request and experiment')
    if profile and inherited_profile and profile != inherited_profile:
        raise ValueError('explicit runtime profiles differ between request and experiment')
    return path(config_path or inherited_path or '.fruitfly/default-config.yaml'), profile or inherited_profile
