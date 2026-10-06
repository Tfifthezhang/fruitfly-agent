"""Private JSONL IPython kernel used by :mod:`fruitfly_agent.lab.context_manager.externalization.programmatic_context`.

The subprocess owns model-generated Python state.  Protocol messages use the
original stdout handle; cell stdout/stderr are captured and returned as data.
"""

from __future__ import annotations

import asyncio
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import sys
import traceback
import uuid
from typing import Any

from IPython.core.interactiveshell import InteractiveShell

from .artifacts import ContextWorkspace, SessionArtifactStore


PROTOCOL_VERSION = 1
_PROTOCOL_STDOUT = sys.stdout


class KernelProtocol:
    def __init__(self) -> None:
        self.pending_host: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self.active: asyncio.Task[None] | None = None
        self.shell = InteractiveShell.instance()
        self.shell.autoawait = True
        root = Path(os.environ["FRUITFLY_RLM_ARTIFACT_ROOT"])
        max_bytes = int(os.environ["FRUITFLY_RLM_MAX_ARTIFACT_BYTES"])
        context = ContextWorkspace(
            SessionArtifactStore(root, max_artifact_bytes=max_bytes)
        )

        async def llm_query(
            prompt: str,
            *,
            system_prompt: str = "",
            max_output_tokens: int | None = None,
        ) -> dict[str, Any]:
            if not isinstance(prompt, str) or not prompt:
                raise ValueError("llm_query prompt must be a non-empty string")
            if not isinstance(system_prompt, str):
                raise TypeError("system_prompt must be a string")
            if max_output_tokens is not None and (
                isinstance(max_output_tokens, bool)
                or not isinstance(max_output_tokens, int)
                or max_output_tokens < 1
            ):
                raise ValueError("max_output_tokens must be a positive integer")
            return await self.host_request(
                "model.query",
                {
                    "prompt": prompt,
                    "system_prompt": system_prompt,
                    "max_output_tokens": max_output_tokens,
                },
            )

        self.shell.push(
            {
                "context": context,
                "llm_query": llm_query,
            }
        )

    def send(self, event: dict[str, Any]) -> None:
        _PROTOCOL_STDOUT.write(json.dumps(event, ensure_ascii=False) + "\n")
        _PROTOCOL_STDOUT.flush()

    async def host_request(
        self, request_type: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        request_id = uuid.uuid4().hex
        future = asyncio.get_running_loop().create_future()
        self.pending_host[request_id] = future
        self.send(
            {
                "event": "host_request",
                "id": request_id,
                "request_type": request_type,
                "payload": payload,
            }
        )
        try:
            reply = await future
        finally:
            self.pending_host.pop(request_id, None)
        if reply.get("status") == "ok":
            result = reply.get("result")
            if not isinstance(result, dict):
                raise RuntimeError("host returned an invalid result")
            return result
        raise RuntimeError(str(reply.get("error") or "host request failed"))

    async def execute(self, request_id: str, code: str) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        status = "ok"
        result_text = ""
        error: dict[str, Any] | None = None
        try:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                transformed = self.shell.transform_cell(code)
                result = await self.shell.run_cell_async(
                    code,
                    store_history=True,
                    silent=False,
                    transformed_cell=transformed,
                )
            failure = result.error_before_exec or result.error_in_exec
            if failure is not None:
                status = "error"
                error = {
                    "type": type(failure).__name__,
                    "message": str(failure),
                }
            elif result.result is not None:
                try:
                    result_text = repr(result.result)
                except Exception as exc:  # pragma: no cover - hostile repr
                    result_text = f"<repr failed: {type(exc).__name__}: {exc}>"
        except asyncio.CancelledError:
            status = "cancelled"
            error = {"type": "CancelledError", "message": "execution cancelled"}
        except BaseException as exc:  # keep protocol alive after a bad cell
            status = "error"
            error = {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            }
        finally:
            self.send(
                {
                    "event": "done",
                    "id": request_id,
                    "status": status,
                    "stdout": stdout.getvalue(),
                    "stderr": stderr.getvalue(),
                    "result": result_text,
                    "error": error,
                }
            )
            self.active = None

    async def dispatch(self, request: dict[str, Any]) -> bool:
        request_type = request.get("type")
        if request_type == "execute":
            request_id = request.get("id")
            code = request.get("code")
            if not isinstance(request_id, str) or not request_id:
                self.send({"event": "protocol_error", "error": "execute requires id"})
            elif not isinstance(code, str):
                self.send(
                    {
                        "event": "done",
                        "id": request_id,
                        "status": "error",
                        "stdout": "",
                        "stderr": "",
                        "result": "",
                        "error": {"type": "TypeError", "message": "code must be a string"},
                    }
                )
            elif self.active is not None:
                self.send(
                    {
                        "event": "done",
                        "id": request_id,
                        "status": "error",
                        "stdout": "",
                        "stderr": "",
                        "result": "",
                        "error": {"type": "RuntimeError", "message": "kernel is busy"},
                    }
                )
            else:
                self.active = asyncio.create_task(self.execute(request_id, code))
            return True
        if request_type == "host_reply":
            request_id = request.get("id")
            future = self.pending_host.get(str(request_id))
            if future is not None and not future.done():
                future.set_result(request)
            return True
        if request_type == "interrupt":
            if self.active is not None:
                self.active.cancel()
            return True
        if request_type == "shutdown":
            if self.active is not None:
                self.active.cancel()
                await asyncio.gather(self.active, return_exceptions=True)
            for future in self.pending_host.values():
                if not future.done():
                    future.set_exception(RuntimeError("kernel is shutting down"))
            return False
        self.send(
            {
                "event": "protocol_error",
                "error": f"unknown request type: {request_type!r}",
            }
        )
        return True


async def _main() -> None:
    protocol = KernelProtocol()
    protocol.send({"event": "ready", "protocol_version": PROTOCOL_VERSION})
    keep_running = True
    while keep_running:
        line = await asyncio.to_thread(sys.stdin.readline)
        if not line:
            break
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                raise TypeError("request must be an object")
        except (json.JSONDecodeError, TypeError) as exc:
            protocol.send({"event": "protocol_error", "error": str(exc)})
            continue
        keep_running = await protocol.dispatch(request)
    if protocol.active is not None:
        protocol.active.cancel()
        await asyncio.gather(protocol.active, return_exceptions=True)
    InteractiveShell.clear_instance()


if __name__ == "__main__":
    asyncio.run(_main())
