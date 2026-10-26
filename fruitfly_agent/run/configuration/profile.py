"""Compatibility entry for the shared, owner-neutral harness configuration."""
from fruitfly_agent.runtime_spec.profiles import (
    DEFAULT_HARNESS_CONFIG_NAME, HARNESS_PROFILE_SCHEMA_VERSION, HarnessConfig, HarnessProfile,
    save_harness_config as save_specification,
)
from fruitfly_agent.lab.catalog import load_system_config, component_profile, builtin_catalog
from dataclasses import replace


def load_harness_config(path, *, catalog=None):
    return load_system_config(path, catalog=catalog)


def save_harness_config(path, config, *, catalog=None, artifact_reader=None):
    if config.schema_version == 2:
        catalog = catalog or builtin_catalog()
        config = replace(config, profiles={key: component_profile(profile, catalog, artifact_reader=artifact_reader)
                                          for key, profile in config.profiles.items()})
    save_specification(path, config)

__all__ = ["DEFAULT_HARNESS_CONFIG_NAME", "HARNESS_PROFILE_SCHEMA_VERSION", "HarnessConfig",
           "HarnessProfile", "load_harness_config", "save_harness_config"]
