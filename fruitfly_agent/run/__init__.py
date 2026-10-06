"""Profile-driven composition root and stable CLI entry point."""

from .assembly import (
    RuntimeAssembly,
    RuntimeManifest,
    build_runtime,
)
from .application import RunApplicationFactory
from .artifacts import (
    DataArtifactRef,
    DataArtifactStore,
)
from .evaluation import RunEvaluationController
from .cli import create_parser, main, resolve_session_path, run_cli
from .profiles import (
    HarnessSelection,
    RunConfigurationController,
    default_model_catalog_path,
    model_catalog_path,
    resolve_harness_selection,
    resolve_profile_models,
)
from .configuration import (
    HarnessConfig,
    HarnessProfile,
    load_harness_config,
    save_harness_config,
)

__all__ = [
    "RuntimeAssembly",
    "RuntimeManifest",
    "RunApplicationFactory",
    "DataArtifactRef",
    "DataArtifactStore",
    "RunEvaluationController",
    "build_runtime",
    "HarnessSelection",
    "RunConfigurationController",
    "default_model_catalog_path",
    "model_catalog_path",
    "resolve_harness_selection",
    "resolve_profile_models",
    "HarnessConfig",
    "HarnessProfile",
    "load_harness_config",
    "save_harness_config",
    "create_parser",
    "resolve_session_path",
    "run_cli",
    "main",
]
