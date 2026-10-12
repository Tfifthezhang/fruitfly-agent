"""Exact assembled runtime identity and supported serialization forms."""
import hashlib
import json
from fruitfly_agent.lab.base_prompt import DEFAULT_PROMPT_ID
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

    def legacy_dict(self, schema_version: int) -> dict[str, Any]:
        """Reconstruct a pre-prompt manifest only for known default sessions."""
        if schema_version not in (3, 4):
            raise ValueError("unsupported legacy runtime manifest schema")
        if self.base_prompt["reference"] != DEFAULT_PROMPT_ID:
            raise ValueError("legacy sessions require the built-in default prompt")
        if any("implementation_id" in item for item in self.components):
            raise ValueError("legacy runtime algorithm identity cannot be verified; start a new session")
        result = self.to_dict()
        result.pop("base_prompt")
        result["schema_version"] = schema_version
        if schema_version == 3:
            result.pop("data_artifacts", None)
        payload = {key: value for key, value in result.items() if key != "digest"}
        result["digest"] = digest_manifest(payload)
        return result


def digest_manifest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()

