"""One-variable mechanism ablation study."""

from __future__ import annotations

from typing import Any, Mapping

from ..contracts import EvaluationRequest


class MechanismComparisonStudy:
    mode = "mechanism_comparison"

    def conditions(
        self,
        request: EvaluationRequest,
    ) -> tuple[Mapping[str, Any], ...]:
        if request.comparison is None:
            raise ValueError("comparison selection is required")
        mechanism_id = request.comparison.mechanism_id
        manifest = request.runtime.manifest
        components = manifest.get("components")
        if not isinstance(components, list):
            raise ValueError("runtime manifest components must be a list")
        selected = [item for item in components if isinstance(item, Mapping)]
        target = next((item for item in selected if item.get("id") == mechanism_id), None)
        if target is None:
            raise ValueError(f"mechanism {mechanism_id!r} is not active")
        contributions = target.get("contributions", [])
        if not any(
            isinstance(item, Mapping) and item.get("layer") != "capability"
            for item in contributions
        ):
            raise ValueError("capability components cannot be the comparison variable")
        dependents = sorted(
            str(item.get("id"))
            for item in selected
            if item.get("id") != mechanism_id
            and isinstance(item.get("requires"), list)
            and mechanism_id in item["requires"]
        )
        if dependents:
            raise ValueError(
                f"cannot remove {mechanism_id!r}; active mechanisms require it: "
                + ", ".join(dependents)
            )
        manifest_digest = manifest.get("digest")
        return (
            {
                "condition_id": "baseline",
                "label": f"Without {mechanism_id}",
                "base_runtime_manifest_digest": manifest_digest,
                "mechanism_overrides": {mechanism_id: {"enabled": False}},
            },
            {
                "condition_id": "candidate",
                "label": "Current setup",
                "base_runtime_manifest_digest": manifest_digest,
                "mechanism_overrides": {},
            },
        )


__all__ = ["MechanismComparisonStudy"]
