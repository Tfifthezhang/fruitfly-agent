"""Value objects shared by execution-environment protocols and implementations."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FileInfo:
    """Portable metadata returned by environment filesystem operations."""

    name: str
    path: str
    kind: str  # "file" | "directory" | "symlink"
    size: int = 0
    mtime_ms: float = 0.0


@dataclass(frozen=True)
class ExecResult:
    """Completed shell-process result, including timeout cancellation state."""

    stdout: str
    stderr: str
    exit_code: int
    cancelled: bool = False


@dataclass(frozen=True)
class ExecOptions:
    """Options for one shell invocation."""

    cwd: str | None = None
    env: dict[str, str] | None = None
    inherit_env: bool = True
    timeout_seconds: float | None = None
    on_stdout: object | None = None  # async callback (chunk: str) -> None
    on_stderr: object | None = None


__all__ = ["FileInfo", "ExecResult", "ExecOptions"]
