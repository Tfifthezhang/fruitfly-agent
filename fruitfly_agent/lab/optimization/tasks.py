"""Explicit, bounded task examples for optimization text search."""

from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
from .search import TaskCase

@dataclass(frozen=True)
class TaskSuite:
    train: tuple[TaskCase, ...]
    validation: tuple[TaskCase, ...]
    digest: str


def load_task_cases(workspace: Path, path: str) -> TaskSuite:
    """Read an explicit, small JSON task suite without following symlinks."""

    root = workspace.resolve()
    requested = Path(path)
    unresolved = root / requested if not requested.is_absolute() else requested
    if unresolved.is_symlink():
        raise ValueError("optimization cases file must not be a symlink")
    source = unresolved.resolve()
    try:
        source.relative_to(root)
    except ValueError as exc:
        raise ValueError("optimization cases path must stay inside the workspace") from exc
    if not source.is_file():
        raise ValueError(f"optimization cases file is unavailable: {source}")
    with source.open("rb") as stream:
        encoded = stream.read(100_001)
    if len(encoded) > 100_000:
        raise ValueError("optimization cases file exceeds 100 KB")
    payload = json.loads(encoded.decode("utf-8"))
    if not isinstance(payload, dict) or set(payload) != {"train", "validation"}:
        raise ValueError("optimization cases require train and validation arrays")

    def parse(name: str) -> tuple[TaskCase, ...]:
        rows = payload[name]
        if not isinstance(rows, list) or not 1 <= len(rows) <= 12:
            raise ValueError(f"optimization {name} must contain 1–12 cases")
        cases: list[TaskCase] = []
        for row in rows:
            if not isinstance(row, dict) or set(row) != {"input", "expected"}:
                raise ValueError(f"optimization {name} cases require input and expected")
            if not all(isinstance(row[key], str) for key in ("input", "expected")):
                raise ValueError(f"optimization {name} case fields must be strings")
            cases.append(TaskCase(row["input"], row["expected"]))
        return tuple(cases)

    train, validation = parse("train"), parse("validation")
    if {case.input for case in train} & {case.input for case in validation}:
        raise ValueError("optimization train and validation inputs must not overlap")
    return TaskSuite(
        train,
        validation,
        "sha256:" + hashlib.sha256(encoded).hexdigest(),
    )

