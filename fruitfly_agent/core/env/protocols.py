"""Stable protocols through which tools access filesystems and shells.

Expected external failures are returned as ``Result.failure`` rather than
raised. Hard asyncio task cancellation remains allowed to propagate after an
implementation has cleaned up its resources.
"""

from __future__ import annotations

from typing import Protocol

from ..errors import Result
from .types import ExecOptions, ExecResult, FileInfo


class FileSystem(Protocol):
    """Filesystem capability exposed to tools."""

    cwd: str

    def absolute_path(self, path: str) -> Result[str]: ...

    def join_path(self, parts: list[str]) -> Result[str]: ...

    def read_text_file(self, path: str) -> Result[str]: ...

    def read_binary_file(self, path: str) -> Result[bytes]: ...

    def write_file(self, path: str, content: str | bytes) -> Result[None]: ...

    def append_file(self, path: str, content: str) -> Result[None]: ...

    def rename_file(self, source: str, destination: str) -> Result[None]: ...

    def file_info(self, path: str) -> Result[FileInfo]: ...

    def list_dir(self, path: str) -> Result[list[FileInfo]]: ...

    def canonical_path(self, path: str) -> Result[str]: ...

    def exists(self, path: str) -> Result[bool]: ...

    def create_dir(self, path: str, recursive: bool = True) -> Result[None]: ...

    def remove(self, path: str, recursive: bool = False) -> Result[None]: ...

    def create_temp_dir(self, prefix: str = "tmp-") -> Result[str]: ...

    def create_temp_file(self, prefix: str = "", suffix: str = "") -> Result[str]: ...


class Shell(Protocol):
    """Asynchronous shell-execution capability exposed to tools."""

    async def exec(self, command: str, options: ExecOptions | None = None) -> Result[ExecResult]: ...


class ExecutionEnv(FileSystem, Shell, Protocol):
    """Complete environment capability injected into a tool call."""


__all__ = ["FileSystem", "Shell", "ExecutionEnv"]
