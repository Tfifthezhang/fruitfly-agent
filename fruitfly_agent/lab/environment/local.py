"""Local execution environment backed by the host filesystem and shell.

Environment implementations are organized by environment, not by protocol
method group: a small implementation stays in one module so adding another
environment adds one obvious entry such as ``container.py`` or ``readonly.py``.
If one implementation becomes too large to read as a single unit, promote it
to a same-named package (for example ``env/container/`` with ``filesystem.py``,
``shell.py`` and ``lifecycle.py``) instead of adding many sibling
``container_*`` modules here.

``LocalEnv`` intentionally implements both Core ``FileSystem`` and ``Shell``
capabilities in this file. It is a local adapter, not a security sandbox.
"""

from __future__ import annotations

import asyncio
import codecs
import os
import shutil
import signal
import tempfile
from pathlib import Path

from fruitfly_agent.core.env import ExecOptions, ExecResult, FileInfo
from fruitfly_agent.core.errors import Result


class LocalEnv:
    """Host filesystem and shell implementation of the Core environment contract.

    Relative filesystem paths are rooted at ``cwd``. Absolute paths and parent
    traversal are deliberately not confined, so callers must wrap or replace
    this implementation when they need a security boundary.
    """

    def __init__(self, cwd: str | None = None) -> None:
        self.cwd = str(Path(cwd).resolve() if cwd else Path.cwd())

    # -- paths -----------------------------------------------------------

    def _resolve(self, path: str) -> Path:
        resolved = Path(path)
        if not resolved.is_absolute():
            resolved = Path(self.cwd) / resolved
        return resolved

    def absolute_path(self, path: str) -> Result[str]:
        try:
            return Result.success(str(self._resolve(path)))
        except Exception as exc:  # noqa: BLE001
            return Result.failure(f"absolute_path failed: {exc}")

    def join_path(self, parts: list[str]) -> Result[str]:
        try:
            return Result.success(str(Path(*parts)))
        except Exception as exc:  # noqa: BLE001
            return Result.failure(f"join_path failed: {exc}")

    # -- filesystem ------------------------------------------------------

    def read_text_file(self, path: str) -> Result[str]:
        try:
            return Result.success(self._resolve(path).read_text(encoding="utf-8", errors="replace"))
        except Exception as exc:  # noqa: BLE001
            return Result.failure(f"read_text_file {path}: {exc}")

    def read_binary_file(self, path: str) -> Result[bytes]:
        try:
            return Result.success(self._resolve(path).read_bytes())
        except Exception as exc:  # noqa: BLE001
            return Result.failure(f"read_binary_file {path}: {exc}")

    def write_file(self, path: str, content: str | bytes) -> Result[None]:
        try:
            resolved = self._resolve(path)
            resolved.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                resolved.write_bytes(content)
            else:
                resolved.write_text(content, encoding="utf-8")
            return Result.success(None)
        except Exception as exc:  # noqa: BLE001
            return Result.failure(f"write_file {path}: {exc}")

    def append_file(self, path: str, content: str) -> Result[None]:
        try:
            resolved = self._resolve(path)
            resolved.parent.mkdir(parents=True, exist_ok=True)
            with resolved.open("a", encoding="utf-8") as file:
                file.write(content)
            return Result.success(None)
        except Exception as exc:  # noqa: BLE001
            return Result.failure(f"append_file {path}: {exc}")

    def rename_file(self, source: str, destination: str) -> Result[None]:
        try:
            self._resolve(source).replace(self._resolve(destination))
            return Result.success(None)
        except Exception as exc:  # noqa: BLE001
            return Result.failure(f"rename_file {source}: {exc}")

    def file_info(self, path: str) -> Result[FileInfo]:
        try:
            resolved = self._resolve(path)
            stat = resolved.lstat()
            kind = "file"
            if resolved.is_dir():
                kind = "directory"
            elif resolved.is_symlink():
                kind = "symlink"
            return Result.success(
                FileInfo(
                    name=resolved.name,
                    path=str(resolved),
                    kind=kind,
                    size=stat.st_size,
                    mtime_ms=stat.st_mtime * 1000,
                )
            )
        except Exception as exc:  # noqa: BLE001
            return Result.failure(f"file_info {path}: {exc}")

    def list_dir(self, path: str) -> Result[list[FileInfo]]:
        try:
            entries = []
            for child in sorted(self._resolve(path).iterdir(), key=lambda candidate: candidate.name):
                info = self.file_info(str(child))
                if info.is_ok:
                    entries.append(info.unwrap())
            return Result.success(entries)
        except Exception as exc:  # noqa: BLE001
            return Result.failure(f"list_dir {path}: {exc}")

    def canonical_path(self, path: str) -> Result[str]:
        try:
            return Result.success(str(self._resolve(path).resolve()))
        except Exception as exc:  # noqa: BLE001
            return Result.failure(f"canonical_path {path}: {exc}")

    def exists(self, path: str) -> Result[bool]:
        try:
            return Result.success(self._resolve(path).exists())
        except Exception as exc:  # noqa: BLE001
            return Result.failure(f"exists {path}: {exc}")

    def create_dir(self, path: str, recursive: bool = True) -> Result[None]:
        try:
            self._resolve(path).mkdir(parents=recursive, exist_ok=True)
            return Result.success(None)
        except Exception as exc:  # noqa: BLE001
            return Result.failure(f"create_dir {path}: {exc}")

    def remove(self, path: str, recursive: bool = False) -> Result[None]:
        try:
            resolved = self._resolve(path)
            if recursive and resolved.is_dir():
                shutil.rmtree(resolved)
            elif resolved.is_dir():
                resolved.rmdir()
            else:
                resolved.unlink(missing_ok=True)
            return Result.success(None)
        except Exception as exc:  # noqa: BLE001
            return Result.failure(f"remove {path}: {exc}")

    def create_temp_dir(self, prefix: str = "tmp-") -> Result[str]:
        try:
            return Result.success(tempfile.mkdtemp(prefix=prefix))
        except Exception as exc:  # noqa: BLE001
            return Result.failure(f"create_temp_dir: {exc}")

    def create_temp_file(self, prefix: str = "", suffix: str = "") -> Result[str]:
        try:
            descriptor, path = tempfile.mkstemp(prefix=prefix, suffix=suffix)
            os.close(descriptor)
            return Result.success(path)
        except Exception as exc:  # noqa: BLE001
            return Result.failure(f"create_temp_file: {exc}")

    # -- shell -----------------------------------------------------------

    async def exec(self, command: str, options: ExecOptions | None = None) -> Result[ExecResult]:
        opts = options or ExecOptions()
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                cwd=opts.cwd if opts.cwd is not None else self.cwd,
                env=self._merge_env(opts),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
        except Exception as exc:  # noqa: BLE001
            return Result.failure(f"spawn failed: {exc}")

        timeout_task: asyncio.Task | None = None
        try:
            drain: asyncio.Task[tuple[str, str]] = asyncio.create_task(
                self._drain(process, opts), name="exec-drain"
            )
            if opts.timeout_seconds is not None and opts.timeout_seconds > 0:
                timeout_task = asyncio.create_task(
                    asyncio.sleep(opts.timeout_seconds), name="exec-timeout"
                )
                pending = {timeout_task, drain}
            else:
                pending = {drain}
            cancelled = False
            while pending:
                done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                if timeout_task in done and not drain.done():
                    cancelled = True
                    self._kill_group(process)
                if drain in done:
                    break
                for task in done:
                    if task is drain:
                        continue
                    task.cancel()
            stdout, stderr = await drain
            exit_code = await process.wait()
            return Result.success(
                ExecResult(stdout=stdout, stderr=stderr, exit_code=exit_code, cancelled=cancelled)
            )
        except asyncio.CancelledError:
            self._kill_group(process)
            try:
                await asyncio.wait_for(drain, timeout=5)
            except (asyncio.TimeoutError, Exception):  # noqa: BLE001
                pass
            raise
        except Exception as exc:  # noqa: BLE001
            self._kill_group(process)
            return Result.failure(f"exec failed: {exc}")
        finally:
            if timeout_task is not None and not timeout_task.done():
                timeout_task.cancel()

    @staticmethod
    def _merge_env(opts: ExecOptions) -> dict[str, str] | None:
        if not opts.inherit_env:
            return opts.env
        merged = dict(os.environ)
        if opts.env:
            merged.update(opts.env)
        return merged

    @staticmethod
    def _kill_group(process: asyncio.subprocess.Process) -> None:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                process.kill()
            except Exception:  # noqa: BLE001
                pass

    @staticmethod
    async def _drain(process: asyncio.subprocess.Process, opts: ExecOptions) -> tuple[str, str]:
        """Drain both pipes before returning; callback failures are isolated."""

        async def read_stream(stream: asyncio.StreamReader | None, callback) -> str:
            if stream is None:
                return ""
            parts: list[str] = []
            decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
            while True:
                chunk = await stream.read(64 * 1024)
                text = decoder.decode(chunk, final=not chunk)
                if text:
                    parts.append(text)
                    if callback is not None:
                        try:
                            await callback(text)
                        except Exception:  # callback failure cannot break draining
                            pass
                if not chunk:
                    break
            return "".join(parts)

        stdout_text, stderr_text = await asyncio.gather(
            read_stream(process.stdout, opts.on_stdout),
            read_stream(process.stderr, opts.on_stderr),
        )
        return stdout_text, stderr_text


__all__ = ["LocalEnv"]
