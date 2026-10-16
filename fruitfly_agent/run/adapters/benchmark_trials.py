"""Optional external task execution without importing Eval into the runtime graph."""
from __future__ import annotations

import asyncio
import codecs
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
from uuid import uuid4


class BenchmarkTrialClient:
    def __init__(self, *, workspace, environment, python_executable=None, on_event=None):
        self.workspace, self.environment = Path(workspace).resolve(), dict(environment)
        self.python_executable = python_executable or sys.executable
        self.on_event = on_event
        self.runtime = None
        self.benchmark_id = None
        self.materials = {}
        self.source_root = None
        self.runtime_hashes = {}

    def configure(self, *, runtime, benchmark_id, materials, source_root, runtime_hashes=None):
        self.runtime, self.benchmark_id = runtime, benchmark_id
        self.materials, self.source_root = dict(materials), Path(source_root)
        self.runtime_hashes = dict(runtime_hashes or {})

    def owned_path(self, path):
        path = Path(path)
        if not path.is_absolute():
            path = self.workspace / path
        if not path.resolve().is_relative_to(self.workspace) or any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError("external evidence must remain in its owned workspace")
        return path

    async def run(self, task, packet, *, timeout, signal=None):
        for path, expected in self.runtime_hashes.items():
            if "sha256:" + hashlib.sha256(self.owned_path(path).read_bytes()).hexdigest() != expected:
                raise ValueError("frozen runtime configuration or model catalog changed")
        root = self.owned_path(self.workspace / ".fruitfly/improvement/experiments/trials" / uuid4().hex)
        root.parent.mkdir(parents=True, exist_ok=True)
        request_path = root.with_suffix(".request.json")
        request = {"schema_version": 1, "runtime": self.runtime, "benchmark_id": self.benchmark_id,
                   "task": task.to_dict(), "task_path": str(self.owned_path(self.materials[task.reference_id])),
                   "source_root": str(self.owned_path(self.source_root)), "packet": packet,
                   "timeout_seconds": timeout}
        request_path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
        try:
            result = await self._execute(("trial", "--request", str(request_path), "--output-root", str(root), "--events", "jsonl"),
                                         root=root, timeout=timeout, signal=signal, result_type="trial-result")
            self.owned_path(result["evidence_root"])
            return result
        finally:
            request_path.unlink(missing_ok=True)

    async def prepare_tasks(self, selection):
        root = self.owned_path(self.workspace / ".fruitfly/improvement/task-sources" / uuid4().hex)
        root.parent.mkdir(parents=True, exist_ok=True)
        result = await self._execute(("prepare", "--benchmark", selection["benchmark_id"],
            "--variant", selection["variant"], "--task-limit", str(selection["task_limit"]),
            "--output-root", str(root), "--events", "jsonl"), root=root,
            timeout=900, result_type="task-set-prepared")
        if self.owned_path(result["material_root"]) != root:
            raise ValueError("prepared task material root differs from the owned request")
        return result

    async def _execute(self, arguments, *, root, timeout, signal=None, result_type):
        environment = {**os.environ, **self.environment}
        source = str(Path(__file__).resolve().parents[3])
        environment["PYTHONPATH"] = source + (os.pathsep + environment["PYTHONPATH"] if environment.get("PYTHONPATH") else "")
        process = await asyncio.create_subprocess_exec(self.python_executable, "-m", "eval", *arguments,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=self.workspace,
            env=environment, start_new_session=True)
        async def emit(event):
            if self.on_event is not None:
                try:
                    await self.on_event(event)
                except Exception:
                    pass  # Observation cannot abort authorized task work.

        async def consume_stderr():
            assert process.stderr is not None
            decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
            while chunk := await process.stderr.read(65536):
                await emit({"type": "log", "source": "eval stderr", "text": decoder.decode(chunk)})
            tail = decoder.decode(b"", final=True)
            if tail:
                await emit({"type": "log", "source": "eval stderr", "text": tail})

        async def consume():
            result = None
            assert process.stdout is not None
            async for line in process.stdout:
                try:
                    value = json.loads(line)
                except ValueError:
                    await emit({"type": "log", "source": "eval stdout",
                                "text": line.decode("utf-8", errors="replace")})
                    continue
                if isinstance(value, dict) and value.get("type") == result_type:
                    result = value
                elif isinstance(value, dict):
                    await emit(value)
            await process.wait()
            return result
        # Drain stderr concurrently so setup failures cannot block a full pipe.
        stderr = asyncio.create_task(consume_stderr())
        work = asyncio.create_task(consume())
        abort = asyncio.create_task(signal.wait()) if signal is not None else None
        try:
            watched = {work} | ({abort} if abort else set())
            done, _ = await asyncio.wait(watched, timeout=timeout + 10, return_when=asyncio.FIRST_COMPLETED)
            if abort in done:
                raise asyncio.CancelledError("external trial cancelled")
            if work not in done:
                raise TimeoutError("external task deadline reached")
            result = await work
            await stderr
            if process.returncode or result is None:
                raise RuntimeError("external task process failed; inspect " + str(root))
            return result
        finally:
            if process.returncode is None:
                try:
                    os.killpg(process.pid, signal_module.SIGINT)
                    await asyncio.wait_for(process.wait(), 5)
                except (ProcessLookupError, TimeoutError):
                    if process.returncode is None:
                        os.killpg(process.pid, signal_module.SIGKILL)
                        await process.wait()
            for pending in (work, stderr, abort):
                if pending is not None and not pending.done():
                    pending.cancel()
            await asyncio.gather(*(p for p in (work, stderr, abort) if p is not None), return_exceptions=True)

    def read_evidence(self, result, artifact):
        root = self.owned_path(result["evidence_root"])
        path = self.owned_path(root / artifact.path)
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("task evidence path escapes its receipt directory")
        if path.stat().st_size > 64 * 1024 * 1024:
            raise ValueError("evidence exceeds the material reader's 64 MB bound")
        body = path.read_bytes()
        if "sha256:" + hashlib.sha256(body).hexdigest() != artifact.digest:
            raise ValueError("task evidence content hash changed")
        return body.decode("utf-8")

    def runtime_receipt(self, result):
        from fruitfly_agent.lab.improvement.api import TaskRunEvidence
        receipt = TaskRunEvidence.from_dict(result["evidence"])
        artifacts = [a for a in receipt.artifacts if a.kind == "runtime-receipt"]
        if len(artifacts) != 1:
            raise ValueError("external trial needs one attributable invocation receipt")
        return json.loads(self.read_evidence(result, artifacts[0]))


signal_module = signal
