"""Host-side lifecycle and JSONL transport for the persistent IPython process."""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
import json
import os
from pathlib import Path
import sys
import uuid
from typing import Any, Awaitable, Callable

from .artifacts import SessionArtifactStore


HostRequestHandler = Callable[
    [str, dict[str, Any], asyncio.Event | None], Awaitable[dict[str, Any]]
]


@dataclass(frozen=True)
class ProgramExecutionResult:
    status: str
    stdout: str
    stderr: str
    result: str
    error: dict[str, Any] | None = None
    output_reference: str | None = None
    truncated: bool = False


class IpythonRuntime:
    """One restartable IPython namespace owned by one assembled Runtime."""

    def __init__(
        self,
        *,
        cwd: Path,
        artifact_store: SessionArtifactStore,
        host_handler: HostRequestHandler,
        max_output_chars: int,
        timeout_seconds: int,
        process_environment: dict[str, str] | None = None,
    ) -> None:
        self.cwd = cwd.resolve()
        self.process_environment = dict(process_environment or {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"})
        self.artifact_store = artifact_store
        self.host_handler = host_handler
        self.max_output_chars = max_output_chars
        self.timeout_seconds = timeout_seconds
        self._process: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._ready: asyncio.Future[None] | None = None
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._execute_lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()
        self._closed = False
        self._active_signal: asyncio.Event | None = None
        self._stderr_tail: deque[str] = deque(maxlen=100)

    async def start(self) -> None:
        if self._closed:
            raise RuntimeError("IPython runtime is closed")
        if self._process is not None and self._process.returncode is None:
            return
        env = dict(self.process_environment)
        package_root = str(Path(__file__).resolve().parents[5])
        existing_pythonpath = env.get("PYTHONPATH")
        env.update(
            {
                "FRUITFLY_RLM_ARTIFACT_ROOT": str(self.artifact_store.root),
                "FRUITFLY_RLM_MAX_ARTIFACT_BYTES": str(
                    self.artifact_store.max_artifact_bytes
                ),
                "PYTHONPATH": (
                    package_root
                    if not existing_pythonpath
                    else os.pathsep.join((package_root, existing_pythonpath))
                ),
            }
        )
        self._ready = asyncio.get_running_loop().create_future()
        self._process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "fruitfly_agent.lab.context_manager.externalization.programmatic_context.kernel",
            cwd=self.cwd,
            env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._reader_task = asyncio.create_task(self._read_protocol())
        self._stderr_task = asyncio.create_task(self._read_stderr())
        try:
            async with asyncio.timeout(30):
                await self._ready
        except BaseException:
            await self._stop_process()
            raise

    async def execute(
        self,
        code: str,
        *,
        signal: asyncio.Event | None = None,
    ) -> ProgramExecutionResult:
        if not isinstance(code, str) or not code.strip():
            raise ValueError("IPython code must be a non-empty string")
        async with self._execute_lock:
            await self.start()
            request_id = uuid.uuid4().hex
            future = asyncio.get_running_loop().create_future()
            self._pending[request_id] = future
            self._active_signal = signal
            await self._send({"type": "execute", "id": request_id, "code": code})
            signal_task = (
                asyncio.create_task(signal.wait()) if signal is not None else None
            )
            try:
                async with asyncio.timeout(self.timeout_seconds):
                    if signal_task is None:
                        event = await future
                    else:
                        done, _ = await asyncio.wait(
                            {future, signal_task},
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        if signal_task in done and signal.is_set():
                            await self._stop_process()
                            raise asyncio.CancelledError
                        event = future.result()
            except TimeoutError:
                await self._stop_process()
                raise TimeoutError(
                    f"IPython execution exceeded {self.timeout_seconds} seconds"
                ) from None
            finally:
                self._active_signal = None
                self._pending.pop(request_id, None)
                if signal_task is not None:
                    signal_task.cancel()
                    await asyncio.gather(signal_task, return_exceptions=True)
            return self._shape_result(event)

    async def health(self) -> dict[str, Any]:
        return {
            "status": (
                "ready"
                if self._process is not None and self._process.returncode is None
                else "stopped"
            ),
            "pid": self._process.pid if self._process is not None else None,
            "artifact_root": str(self.artifact_store.root),
        }

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._stop_process(graceful=True)

    async def _read_protocol(self) -> None:
        assert self._process is not None and self._process.stdout is not None
        process = self._process
        try:
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                try:
                    event = json.loads(line)
                    if not isinstance(event, dict):
                        raise TypeError("kernel event is not an object")
                except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
                    raise RuntimeError(f"invalid IPython kernel protocol: {exc}") from exc
                kind = event.get("event")
                if kind == "ready":
                    if event.get("protocol_version") != 1:
                        raise RuntimeError(
                            "unsupported IPython kernel protocol version: "
                            f"{event.get('protocol_version')!r}"
                        )
                    if self._ready is not None and not self._ready.done():
                        self._ready.set_result(None)
                elif kind == "done":
                    future = self._pending.get(str(event.get("id")))
                    if future is not None and not future.done():
                        future.set_result(event)
                elif kind == "host_request":
                    asyncio.create_task(self._handle_host_request(event))
                elif kind == "protocol_error":
                    raise RuntimeError(str(event.get("error") or "kernel protocol error"))
                else:
                    raise RuntimeError(f"unknown IPython kernel event: {kind!r}")
        except asyncio.CancelledError:
            raise
        except BaseException as exc:
            self._fail_waiters(exc)
            if process.returncode is None:
                process.kill()
        finally:
            if process.returncode is None:
                await process.wait()
            if not self._closed and process is self._process:
                detail = "".join(self._stderr_tail)[-4_000:]
                self._fail_waiters(
                    RuntimeError(
                        f"IPython kernel exited with code {process.returncode}: {detail}"
                    )
                )

    async def _read_stderr(self) -> None:
        assert self._process is not None and self._process.stderr is not None
        try:
            while True:
                line = await self._process.stderr.readline()
                if not line:
                    return
                self._stderr_tail.append(line.decode("utf-8", errors="replace"))
        except asyncio.CancelledError:
            raise

    async def _handle_host_request(self, event: dict[str, Any]) -> None:
        request_id = event.get("id")
        request_type = event.get("request_type")
        payload = event.get("payload")
        if not isinstance(request_id, str) or not isinstance(request_type, str):
            return
        try:
            if not isinstance(payload, dict):
                raise TypeError("host request payload must be an object")
            result = await self.host_handler(
                request_type,
                payload,
                self._active_signal,
            )
            reply = {
                "type": "host_reply",
                "id": request_id,
                "status": "ok",
                "result": result,
            }
        except asyncio.CancelledError:
            reply = {
                "type": "host_reply",
                "id": request_id,
                "status": "error",
                "error": "host request cancelled",
            }
        except Exception as exc:  # host policy failures become Python exceptions
            reply = {
                "type": "host_reply",
                "id": request_id,
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
            }
        try:
            await self._send(reply)
        except (BrokenPipeError, ConnectionError, RuntimeError):
            pass

    async def _send(self, request: dict[str, Any]) -> None:
        process = self._process
        if process is None or process.returncode is not None or process.stdin is None:
            raise RuntimeError("IPython kernel is not running")
        data = (json.dumps(request, ensure_ascii=False) + "\n").encode("utf-8")
        async with self._write_lock:
            process.stdin.write(data)
            await process.stdin.drain()

    async def _stop_process(self, *, graceful: bool = False) -> None:
        process = self._process
        reader = self._reader_task
        stderr = self._stderr_task
        self._process = None
        self._reader_task = None
        self._stderr_task = None
        if process is None:
            return
        if process.returncode is None and graceful and process.stdin is not None:
            try:
                process.stdin.write(b'{"type":"shutdown"}\n')
                await process.stdin.drain()
                async with asyncio.timeout(2):
                    await process.wait()
            except (BrokenPipeError, ConnectionError, TimeoutError):
                pass
        if process.returncode is None:
            process.kill()
            await process.wait()
        current = asyncio.current_task()
        for task in (reader, stderr):
            if task is not None and task is not current:
                task.cancel()
        await asyncio.gather(
            *(task for task in (reader, stderr) if task is not None and task is not current),
            return_exceptions=True,
        )
        self._fail_waiters(RuntimeError("IPython kernel stopped"))

    def _fail_waiters(self, error: BaseException) -> None:
        if self._ready is not None and not self._ready.done():
            self._ready.set_exception(error)
        for future in self._pending.values():
            if not future.done():
                future.set_exception(error)

    def _shape_result(self, event: dict[str, Any]) -> ProgramExecutionResult:
        stdout = str(event.get("stdout") or "")
        stderr = str(event.get("stderr") or "")
        result = str(event.get("result") or "")
        combined = "".join((stdout, stderr, result))
        reference: str | None = None
        truncated = len(combined) > self.max_output_chars
        if truncated:
            artifact = self.artifact_store.put_text(
                combined,
                kind="ipython-output",
                origin="ipython",
            )
            reference = artifact.reference
            remaining = self.max_output_chars
            stdout = stdout[:remaining]
            remaining -= len(stdout)
            stderr = stderr[: max(0, remaining)]
            remaining -= len(stderr)
            result = result[: max(0, remaining)]
        error = event.get("error")
        return ProgramExecutionResult(
            status=str(event.get("status") or "error"),
            stdout=stdout,
            stderr=stderr,
            result=result,
            error=error if isinstance(error, dict) else None,
            output_reference=reference,
            truncated=truncated,
        )


__all__ = ["HostRequestHandler", "IpythonRuntime", "ProgramExecutionResult"]
