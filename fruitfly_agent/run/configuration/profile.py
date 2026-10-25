"""Compatibility entry for the shared, owner-neutral harness configuration."""
from fruitfly_agent.runtime_spec.profiles import (
    DEFAULT_HARNESS_CONFIG_NAME, HARNESS_PROFILE_SCHEMA_VERSION, HarnessConfig, HarnessProfile,
    load_harness_config, save_harness_config,
)

__all__ = ["DEFAULT_HARNESS_CONFIG_NAME", "HARNESS_PROFILE_SCHEMA_VERSION", "HarnessConfig",
           "HarnessProfile", "load_harness_config", "save_harness_config"]
