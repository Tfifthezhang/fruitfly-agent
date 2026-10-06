"""Study protocol: turn one request into controlled runtime conditions."""

from __future__ import annotations

from typing import Any, Mapping, Protocol

from ..contracts import EvaluationRequest


class EvaluationStudy(Protocol):
    mode: str

    def conditions(
        self,
        request: EvaluationRequest,
    ) -> tuple[Mapping[str, Any], ...]: ...


__all__ = ["EvaluationStudy"]
