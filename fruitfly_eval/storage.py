"""Immutable evaluation artifact layout and atomic JSON writes."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping


class EvaluationStore:
    def __init__(self, root: Path, evaluation_id: str) -> None:
        if not evaluation_id or "/" in evaluation_id or "\\" in evaluation_id:
            raise ValueError("invalid evaluation id")
        self.path = root / evaluation_id
        self.trials = self.path / "trials"
        self.artifacts = self.path / "artifacts"

    def create(self) -> None:
        self.path.mkdir(parents=True, exist_ok=False)
        self.trials.mkdir()
        self.artifacts.mkdir()

    def write_json(self, relative: str, data: Mapping[str, Any]) -> Path:
        target = self.path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{target.name}.", dir=target.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        except BaseException:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            raise
        return target

    def write_text(self, relative: str, text: str) -> Path:
        target = self.path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{target.name}.", dir=target.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        except BaseException:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            raise
        return target


__all__ = ["EvaluationStore"]
