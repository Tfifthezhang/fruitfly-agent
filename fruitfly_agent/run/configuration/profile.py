"""Registered loading and saving for the shared component configuration."""
from fruitfly_agent.runtime_spec.profiles import (
    DEFAULT_HARNESS_CONFIG_NAME, HarnessConfig, HarnessProfile,
    save_harness_config as save_specification,
)
from fruitfly_agent.lab.catalog import load_system_config, component_profile, builtin_catalog
from dataclasses import replace


def load_harness_config(path, *, catalog=None):
    return load_system_config(path, catalog=catalog)


def save_harness_config(path, config, *, catalog=None, artifact_reader=None):
    catalog = catalog or builtin_catalog()
    from pathlib import Path
    from .component_files import prepare_component_files
    from .persistence import FileTransaction, write_bytes
    config, payloads = prepare_component_files(path, config, catalog, artifact_reader)
    for profile in config.profiles.values():
        for source in profile.source_files:
            if not source.path.startswith('package:'):
                source.check()
    files = FileTransaction.capture((*payloads, Path(path)))
    with files.writing((*payloads, Path(path))):
        for target, data in payloads.items():
            write_bytes(target, data)
        save_specification(path, config)

__all__ = ["DEFAULT_HARNESS_CONFIG_NAME", "HarnessConfig",
           "HarnessProfile", "load_harness_config", "save_harness_config"]
