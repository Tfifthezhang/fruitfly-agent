"""Current complete harness condition."""

from __future__ import annotations

from typing import Any, Mapping

from ..contracts import EvaluationRequest


class CurrentSetupStudy:
    mode = "current_setup"

    def conditions(
        self,
        request: EvaluationRequest,
    ) -> tuple[Mapping[str, Any], ...]:
        return (
            {
                "condition_id": "current",
                "label": "Current setup",
                "base_runtime_manifest_digest": request.runtime.manifest.get("digest"),
                "mechanism_overrides": {},
            },
        )


__all__ = ["CurrentSetupStudy"]
