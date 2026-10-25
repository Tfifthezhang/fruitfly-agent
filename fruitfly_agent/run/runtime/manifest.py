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
    execution: Mapping[str, Any] | None = None
    harness: Mapping[str, Any] | None = None

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
        if self.harness is not None:
            result["harness"] = dict(self.harness)
        if self.permissions is not None:
            result["permissions"] = dict(self.permissions)
        if self.execution is not None:
            result['execution'] = dict(self.execution)
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


def execution_version_payload(manifest: Mapping[str, Any], source: str) -> dict[str, Any]:
    """Execution identity excludes the independently versioned improvement strategy."""
    return {**({'execution': manifest['execution']} if 'execution' in manifest else {}),
            "source": source, "components": [c for c in manifest["components"]
            if not any(x.get("layer") == "improvement" for x in c.get("contributions", ()))],
            "context_pipeline": manifest.get("context_pipeline"),
            "base_prompt": {"content_hash": manifest["base_prompt"]["content_hash"]},
            "data_artifacts": sorted((a for a in manifest.get("data_artifacts", ()) if a.get('role', 'H') == 'H'), key=lambda a: a['key'])}

