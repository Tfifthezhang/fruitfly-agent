"""Immutable H/I/S bindings; model, environment and acceptance are external conditions."""
from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import json
import re


def content_hash(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def require_hash(value: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
        raise ValueError("an immutable SHA-256 content reference is required")


@dataclass(frozen=True)
class SystemVersion:
    harness: str
    improver: str
    state: str

    def __post_init__(self) -> None:
        for value in (self.harness, self.improver, self.state):
            require_hash(value)

    @property
    def version_id(self) -> str:
        return content_hash(canonical_json(self.to_dict()))

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> SystemVersion:
        if not isinstance(data, dict) or set(data) != {"harness", "improver", "state"}:
            raise ValueError("system version must bind H, I and S explicitly")
        return cls(**data)


@dataclass(frozen=True)
class SnapshotFile:
    path: str
    content: str

    def __post_init__(self) -> None:
        parts = self.path.split("/") if isinstance(self.path, str) else []
        if (not parts or self.path.startswith("/") or "\\" in self.path
                or any(p in {"", ".", ".."} for p in parts)
                or any(ord(c) < 32 for c in self.path) or not isinstance(self.content, str)):
            raise ValueError("snapshot files require workspace-relative paths and text")

    @property
    def digest(self) -> str:
        return content_hash(self.content)


@dataclass(frozen=True)
class StateSnapshot:
    files: tuple[SnapshotFile, ...] = ()
    update_rule: str = "frozen-per-trial"
    roots: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "files", tuple(sorted(self.files, key=lambda f: f.path)))
        object.__setattr__(self, "roots", tuple(sorted(self.roots)))
        for root in self.roots:
            SnapshotFile(root + "/.snapshot-path-check", "")
        if len(set(self.roots)) != len(self.roots):
            raise ValueError("duplicate state root")
        if len({f.path for f in self.files}) != len(self.files):
            raise ValueError("duplicate state snapshot path")
        if not isinstance(self.update_rule, str) or not self.update_rule.strip():
            raise ValueError("state snapshots must declare their update rule")

    @property
    def snapshot_id(self) -> str:
        return content_hash(canonical_json(self.to_dict()))

    def to_dict(self) -> dict:
        return {"files": [asdict(f) for f in self.files], "update_rule": self.update_rule, "roots": list(self.roots)}

    @classmethod
    def from_dict(cls, data: dict) -> StateSnapshot:
        if not isinstance(data, dict) or set(data) != {"files", "update_rule", "roots"} or not isinstance(data["files"], list):
            raise ValueError("invalid state snapshot")
        return cls(tuple(SnapshotFile(**f) for f in data["files"]), data["update_rule"], tuple(data["roots"]))


STATE_SNAPSHOTS_COMPONENT = "persistent-state-snapshots"
EXPERIMENT_BLOCKERS_COMPONENT = "experiment-blockers"
