"""Evaluation-owned retirement capability shared by compatible process backends."""
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ExecutionControl(Protocol):
    def stop(self, evaluation: Path) -> dict[str, Any]: ...


class HarborControl:
    def stop(self, evaluation: Path) -> dict[str, Any]:
        from fruitfly_eval.harbor.lifecycle import request_stop
        return request_stop(evaluation)
