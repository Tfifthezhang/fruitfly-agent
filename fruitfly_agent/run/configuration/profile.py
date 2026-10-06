"""Strict, versioned harness profiles shared by frontends and Python callers."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping

import yaml

from fruitfly_agent.lab.catalog.models import MechanismSelection
from fruitfly_agent.lab.base_prompt import DEFAULT_PROMPT_ID


HARNESS_PROFILE_SCHEMA_VERSION = 1
DEFAULT_HARNESS_CONFIG_NAME = ".fruitfly/config.yaml"

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


@dataclass(frozen=True)
class HarnessProfile:
    profile_id: str
    model_catalog: str = "models.yaml"
    model_profile: str | None = None
    mechanisms: tuple[MechanismSelection, ...] = ()
    prompt: str = DEFAULT_PROMPT_ID
    artifact_bindings: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _ID.fullmatch(self.profile_id):
            raise ValueError("harness profile id must be a stable identifier")
        if not isinstance(self.model_catalog, str) or not self.model_catalog.strip():
            raise ValueError("model catalog must be a non-empty path")
        if self.model_profile is not None and (
            not isinstance(self.model_profile, str) or not self.model_profile.strip()
        ):
            raise ValueError("model profile must be a non-empty string or null")
        if not isinstance(self.artifact_bindings, Mapping) or any(not isinstance(k, str) or not isinstance(v, str) or not k or not v for k, v in self.artifact_bindings.items()):
            raise ValueError("artifact bindings must map slot names to references")
        object.__setattr__(self, "artifact_bindings", dict(self.artifact_bindings))
        object.__setattr__(self, "mechanisms", tuple(self.mechanisms))
        if not isinstance(self.prompt, str) or not self.prompt.strip():
            raise ValueError("harness profile prompt must be a non-empty reference")

    @property
    def profile_hash(self) -> str:
        encoded = json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return "sha256:" + hashlib.sha256(encoded).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = {
            "model": {
                "catalog": self.model_catalog,
                "profile": self.model_profile,
            },
            "mechanisms": [item.to_dict() for item in self.mechanisms],
        }
        if self.prompt != DEFAULT_PROMPT_ID:
            result["prompt"] = self.prompt
        if self.artifact_bindings:
            result["artifact_bindings"] = dict(self.artifact_bindings)
        return result


@dataclass(frozen=True)
class HarnessConfig:
    default_profile: str
    profiles: Mapping[str, HarnessProfile] = field(default_factory=dict)
    schema_version: int = HARNESS_PROFILE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != HARNESS_PROFILE_SCHEMA_VERSION or isinstance(
            self.schema_version, bool
        ):
            raise ValueError(
                f"unsupported harness profile schema_version: {self.schema_version}"
            )
        profiles = dict(self.profiles)
        if not profiles:
            raise ValueError("harness config requires at least one profile")
        if any(key != value.profile_id for key, value in profiles.items()):
            raise ValueError("harness profile mapping keys must match profile IDs")
        if self.default_profile not in profiles:
            raise ValueError(
                f"unknown default harness profile: {self.default_profile!r}"
            )
        object.__setattr__(self, "profiles", profiles)

    def select(self, profile_id: str | None = None) -> HarnessProfile:
        selected = profile_id or self.default_profile
        try:
            return self.profiles[selected]
        except KeyError as exc:
            available = ", ".join(sorted(self.profiles))
            raise ValueError(
                f"unknown harness profile {selected!r} (available: {available})"
            ) from exc

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "default_profile": self.default_profile,
            "profiles": {
                key: self.profiles[key].to_dict() for key in sorted(self.profiles)
            },
        }


def load_harness_config(path: str | Path) -> HarnessConfig:
    target = Path(path)
    raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, Mapping):
        raise ValueError("harness config must be a mapping")
    _reject_unknown(
        raw,
        {"schema_version", "default_profile", "profiles"},
        "harness config",
    )
    version = raw.get("schema_version")
    if version != HARNESS_PROFILE_SCHEMA_VERSION or isinstance(version, bool):
        raise ValueError(f"unsupported harness profile schema_version: {version}")
    default_profile = raw.get("default_profile")
    if not isinstance(default_profile, str) or not default_profile:
        raise ValueError("harness config default_profile must be a non-empty string")
    raw_profiles = raw.get("profiles")
    if not isinstance(raw_profiles, Mapping):
        raise ValueError("harness config profiles must be a mapping")
    profiles = {
        str(profile_id): _profile_from_mapping(str(profile_id), value)
        for profile_id, value in raw_profiles.items()
    }
    return HarnessConfig(
        default_profile=default_profile,
        profiles=profiles,
        schema_version=version,
    )


def save_harness_config(path: str | Path, config: HarnessConfig) -> None:
    """Atomically replace a public profile file without storing credentials."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = yaml.safe_dump(
        config.to_dict(),
        allow_unicode=True,
        sort_keys=False,
    )
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=target.parent,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except BaseException:
        try:
            Path(temporary).unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _profile_from_mapping(profile_id: str, raw: Any) -> HarnessProfile:
    if not isinstance(raw, Mapping):
        raise ValueError(f"harness profile {profile_id!r} must be a mapping")
    _reject_unknown(raw, {"model", "mechanisms", "prompt", "artifact_bindings"}, f"profile {profile_id!r}")
    model = raw.get("model")
    if not isinstance(model, Mapping):
        raise ValueError(f"profile {profile_id!r} model must be a mapping")
    _reject_unknown(model, {"catalog", "profile"}, "model selection")
    catalog = model.get("catalog", "models.yaml")
    model_profile = model.get("profile")
    raw_mechanisms = raw.get("mechanisms", [])
    if not isinstance(raw_mechanisms, list):
        raise ValueError(f"profile {profile_id!r} mechanisms must be a list")
    mechanisms = tuple(
        _selection_from_mapping(item, index=index)
        for index, item in enumerate(raw_mechanisms)
    )
    return HarnessProfile(
        profile_id=profile_id,
        model_catalog=catalog,
        model_profile=model_profile,
        mechanisms=mechanisms,
        prompt=raw.get("prompt", DEFAULT_PROMPT_ID),
        artifact_bindings=raw.get("artifact_bindings", {}),
    )


def _selection_from_mapping(raw: Any, *, index: int) -> MechanismSelection:
    if not isinstance(raw, Mapping):
        raise ValueError(f"mechanism selection {index} must be a mapping")
    _reject_unknown(raw, {"id", "enabled", "parameters"}, "mechanism selection")
    mechanism_id = raw.get("id")
    if not isinstance(mechanism_id, str):
        raise ValueError(f"mechanism selection {index} id must be a string")
    enabled = raw.get("enabled", True)
    parameters = raw.get("parameters", {})
    return MechanismSelection(mechanism_id, enabled=enabled, parameters=parameters)


def _reject_unknown(
    raw: Mapping[Any, Any], allowed: set[str], location: str
) -> None:
    unknown = sorted(str(key) for key in raw if key not in allowed)
    if unknown:
        raise ValueError(f"unknown {location} fields: {', '.join(unknown)}")


__all__ = [
    "HARNESS_PROFILE_SCHEMA_VERSION",
    "DEFAULT_HARNESS_CONFIG_NAME",
    "HarnessProfile",
    "HarnessConfig",
    "load_harness_config",
    "save_harness_config",
]
