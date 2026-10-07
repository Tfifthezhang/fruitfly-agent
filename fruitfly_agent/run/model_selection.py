"""Discover harness profiles and resolve their model catalog identities."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Mapping

from fruitfly_agent.lab.catalog import LabCatalog
from fruitfly_agent.providers.registry import load_model_specs
from fruitfly_agent.providers.specs import ModelSpec
from fruitfly_agent.providers.workspace import WorkspacePaths

from .configuration import DEFAULT_HARNESS_CONFIG_NAME, HarnessConfig, HarnessProfile, load_harness_config


@dataclass(frozen=True)
class HarnessSelection:
    config: HarnessConfig
    profile: HarnessProfile
    config_path: Path
    persisted: bool


def resolve_harness_selection(
    *,
    cwd: Path,
    config_path: str | None,
    profile_id: str | None,
    environment: Mapping[str, str],
    catalog: LabCatalog,
    allow_incomplete: bool = False,
) -> HarnessSelection:
    """Load an explicit/default config or synthesize the documented baseline."""

    target = _resolve_config_path(cwd, config_path)
    if target.is_file():
        config = load_harness_config(target)
        profile = config.select(profile_id)
        return HarnessSelection(config, profile, target, True)
    if config_path is not None and not allow_incomplete:
        raise ValueError(f"harness config not found: {target}")
    if profile_id is not None:
        raise ValueError("--profile requires a harness config")

    paths = WorkspacePaths(cwd)
    if allow_incomplete and paths.model_catalog() is None:
        return _incomplete_selection(
            target, catalog, _model_catalog_reference(paths.models, target),
        )

    model_catalog = default_model_catalog_path(cwd)
    if model_catalog is None:
        if allow_incomplete:
            return _incomplete_selection(
                target,
                catalog,
                _model_catalog_reference(paths.models, target),
            )
        raise ValueError("no models.yaml found; configure a model catalog")
    models = load_model_specs(model_catalog)
    selected_model = environment.get("FRUITFLY_MODEL_PROFILE")
    if selected_model is not None and not selected_model.strip():
        selected_model = None
    if selected_model is None:
        if len(models) != 1:
            if allow_incomplete:
                return _incomplete_selection(
                    target,
                    catalog,
                    _model_catalog_reference(model_catalog, target),
                )
            available = ", ".join(sorted(models)) or "none"
            raise ValueError(
                "model profile is ambiguous; configure .fruitfly/config.yaml or set "
                f"FRUITFLY_MODEL_PROFILE (available: {available})"
            )
        selected_model = next(iter(models))
    if selected_model not in models:
        available = ", ".join(sorted(models)) or "none"
        raise ValueError(
            f"FRUITFLY_MODEL_PROFILE selects unknown model profile {selected_model!r} "
            f"(available: {available})"
        )
    profile = HarnessProfile(
        profile_id="default",
        model_catalog=_model_catalog_reference(model_catalog, target),
        model_profile=selected_model,
        mechanisms=catalog.default_selections(),
    )
    config = HarnessConfig(default_profile="default", profiles={"default": profile})
    return HarnessSelection(config, profile, target, False)


def default_model_catalog_path(cwd: Path) -> Path | None:
    candidates = (
        WorkspacePaths(cwd).model_catalog(),
        Path(__file__).resolve().parents[2] / "models.yaml",
    )
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate is None:
            continue
        candidate = candidate.resolve()
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.is_file():
            return candidate
    return None


def model_catalog_path(profile: HarnessProfile, config_path: Path) -> Path:
    path = Path(profile.model_catalog)
    if not path.is_absolute():
        path = config_path.parent / path
    return path.resolve()


def resolve_profile_models(
    profile: HarnessProfile,
    config_path: Path,
) -> tuple[dict[str, ModelSpec], str, ModelSpec]:
    path = model_catalog_path(profile, config_path)
    models = load_model_specs(path)
    selected = profile.model_profile
    if selected is None:
        if len(models) != 1:
            available = ", ".join(sorted(models)) or "none"
            raise ValueError(
                f"profile {profile.profile_id!r} model is ambiguous "
                f"(available: {available})"
            )
        selected = next(iter(models))
    try:
        spec = models[selected]
    except KeyError as exc:
        available = ", ".join(sorted(models)) or "none"
        raise ValueError(
            f"unknown model profile {selected!r} (available: {available})"
        ) from exc
    return models, selected, spec



def _resolve_config_path(cwd: Path, value: str | None) -> Path:
    if value is None:
        return (cwd / DEFAULT_HARNESS_CONFIG_NAME).resolve()
    path = Path(value)
    return path.resolve() if path.is_absolute() else (cwd / path).resolve()


def _incomplete_selection(
    target: Path,
    catalog: LabCatalog,
    model_catalog: str,
) -> HarnessSelection:
    profile = HarnessProfile(
        profile_id="default",
        model_catalog=model_catalog,
        model_profile=None,
        mechanisms=catalog.default_selections(),
    )
    config = HarnessConfig(default_profile="default", profiles={"default": profile})
    return HarnessSelection(config, profile, target, False)


def _model_catalog_reference(model_catalog: Path, config_path: Path) -> str:
    return os.path.relpath(
        model_catalog.resolve(),
        start=config_path.parent.resolve(),
    )
