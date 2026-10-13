"""Exact assembled runtime identity and supported serialization forms."""
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

@dataclass(frozen=True)
class RuntimeManifest:
    """Exact, non-secret artifacts used to construct one runtime."""

    schema_version: int
    profile: str
    model_profile: str
    models: Mapping[str, Mapping[str, Any]]
    components: tuple[Mapping[str, Any], ...]
    context_pipeline: Mapping[str, Any] | None
    data_artifacts: tuple[Mapping[str, Any], ...]
    base_prompt: Mapping[str, str]
    digest: str
    permissions: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {
            "schema_version": self.schema_version,
            "profile": self.profile,
            "model_profile": self.model_profile,
            "models": {key: dict(value) for key, value in self.models.items()},
            "components": [dict(value) for value in self.components],
            "context_pipeline": (
                dict(self.context_pipeline) if self.context_pipeline is not None else None
            ),
            "base_prompt": dict(self.base_prompt),
            "digest": self.digest,
        }
        if self.permissions is not None:
            result["permissions"] = dict(self.permissions)
        if self.data_artifacts:
            result["data_artifacts"] = [dict(value) for value in self.data_artifacts]
        return result


def digest_manifest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()

