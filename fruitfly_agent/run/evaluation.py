"""Subprocess bridge from the application shell to the optional eval package."""

from __future__ import annotations

import asyncio
import codecs
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Mapping

from fruitfly_agent.interactive import (
    AgentApplication,
    EvaluationBenchmarkOption,
    EvaluationLaunchRequest,
    EvaluationLaunchResult,
    EvaluationMechanismOption,
    EvaluationModeOption,
    EvaluationSnapshot,
    EvaluationVariantOption,
    EvaluationEventSink,
)

from .application import RunApplicationFactory


SMOKE_EVALUATION_TIMEOUT_SECONDS = 60 * 60
FULL_EVALUATION_TIMEOUT_SECONDS = 7 * 24 * 60 * 60


class RunEvaluationController:
    """Expose eval without importing it into the production runtime graph."""

    def __init__(
        self,
        application: AgentApplication,
        factory: RunApplicationFactory,
        *,
        python_executable: str | None = None,
    ) -> None:
        self.application = application
        self.factory = factory
        self.python_executable = python_executable or sys.executable

    def snapshot(self) -> EvaluationSnapshot:
        import subprocess

        completed = subprocess.run(
            [self.python_executable, "-m", "eval", "catalog", "--json"],
            cwd=self.factory.cwd,
            check=False,
            capture_output=True,
            text=True,
            env=self._environment(),
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or "could not load eval catalog")
        payload = json.loads(completed.stdout)
        modes = tuple(
            EvaluationModeOption(
                str(item["id"]), str(item["label"]), str(item["description"])
            )
            for item in payload.get("modes", [])
        )
        benchmarks = []
        for item in payload.get("benchmarks", []):
            variants = []
            for variant in item.get("variants", []):
                preflight = variant.get("preflight", {})
                checks = preflight.get("checks", [])
                failures = tuple(
                    str(check.get("detail", ""))
                    for check in checks
                    if not check.get("ok", False)
                )
                variants.append(
                    EvaluationVariantOption(
                        str(variant["id"]),
                        str(variant["label"]),
                        str(variant["description"]),
                        bool(preflight.get("available", False)),
                        failures,
                    )
                )
            benchmarks.append(
                EvaluationBenchmarkOption(
                    str(item["id"]),
                    str(item["label"]),
                    str(item["description"]),
                    str(item["version"]),
                    tuple(variants),
                )
            )
        labels = {
            item.mechanism_id: item.label
            for item in self.factory.configuration.snapshot().mechanisms
        }
        mechanisms = []
        for component in self.application.runtime_manifest.get("components", []):
            if not isinstance(component, Mapping):
                continue
            contributions = component.get("contributions", [])
            if not any(
                isinstance(value, Mapping) and value.get("layer") != "capability"
                for value in contributions
            ):
                continue
            mechanism_id = str(component.get("id", ""))
            if mechanism_id:
                mechanisms.append(
                    EvaluationMechanismOption(
                        mechanism_id,
                        labels.get(mechanism_id, mechanism_id),
                    )
                )
        return EvaluationSnapshot(
            modes=modes,
            benchmarks=tuple(benchmarks),
            mechanisms=tuple(mechanisms),
        )

    async def run(
        self, request: EvaluationLaunchRequest,
        on_event: EvaluationEventSink | None = None,
    ) -> EvaluationLaunchResult:
        if self.application.running or self.application.pending_count:
            raise RuntimeError("finish or cancel active work before starting eval")
        manifest = self.application.runtime_manifest
        selection = self.factory.selection
        payload: dict[str, Any] = {
            "schema_version": 1,
            "mode": request.mode,
            "runtime": {
                "manifest": manifest,
                "config_path": str(selection.config_path),
                "profile": selection.profile.profile_id,
                "working_directory": str(self.factory.cwd),
            },
            "benchmark": {"id": request.benchmark_id, "variant": request.variant},
            "comparison": (
                {"mechanism_id": request.mechanism_id}
                if request.mechanism_id is not None
                else None
            ),
            "execution": {
                "attempts": 1,
                "concurrency": 1,
                "seed": 0,
                "timeout_seconds": _default_timeout_seconds(request.variant),
            },
        }
        request_dir = self.factory.cwd / ".fruitfly" / "eval" / ".requests"
        request_dir.mkdir(parents=True, exist_ok=True)
        descriptor, raw_path = tempfile.mkstemp(
            prefix="request-", suffix=".json", dir=request_dir
        )
        path = Path(raw_path)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            process = await asyncio.create_subprocess_exec(
                self.python_executable,
                "-m",
                "eval",
                "run",
                "--request",
                str(path),
                "--events",
                "jsonl",
                cwd=self.factory.cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._environment(),
            )
            async def read_stderr() -> bytes:
                assert process.stderr is not None
                chunks = []
                decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
                while chunk := await process.stderr.read(65536):
                    chunks.append(chunk)
                    if on_event is not None:
                        await on_event({
                            "type": "log", "source": "eval stderr",
                            "text": decoder.decode(chunk),
                        })
                tail = decoder.decode(b"", final=True)
                if tail and on_event is not None:
                    await on_event({"type": "log", "source": "eval stderr", "text": tail})
                return b"".join(chunks)

            stderr_task = asyncio.create_task(read_stderr())
            finished = None
            try:
                assert process.stdout is not None
                async for raw_line in process.stdout:
                    try:
                        value = json.loads(raw_line)
                    except json.JSONDecodeError:
                        if on_event is not None:
                            await on_event({
                                "type": "log", "source": "eval stdout",
                                "text": raw_line.decode("utf-8", errors="replace"),
                            })
                        continue
                    if isinstance(value, Mapping):
                        if value.get("type") == "finished":
                            finished = value
                        if on_event is not None:
                            await on_event(value)
                await process.wait()
                stderr = await stderr_task
            finally:
                if process.returncode is None:
                    process.kill()
                    await process.wait()
                if not stderr_task.done():
                    stderr_task.cancel()
        finally:
            path.unlink(missing_ok=True)
        if finished is None:
            detail = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(detail or f"eval process exited with {process.returncode}")
        return EvaluationLaunchResult(
            status=str(finished.get("status", "failed")),
            evaluation_id=str(finished.get("evaluation_id", "")),
            report_markdown=str(finished.get("report_markdown", "")),
            report_json=str(finished.get("report_json", "")),
            detail=stderr.decode("utf-8", errors="replace").strip(),
        )

    def _environment(self) -> dict[str, str]:
        environment = {**os.environ, **self.factory.environment}
        source_root = str(Path(__file__).resolve().parents[2])
        existing = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = (
            source_root if not existing else os.pathsep.join((source_root, existing))
        )
        return environment


def _default_timeout_seconds(resource_profile: str) -> int:
    """Bound a Harbor job without applying a one-task limit to full datasets."""

    return (
        SMOKE_EVALUATION_TIMEOUT_SECONDS
        if resource_profile == "smoke"
        else FULL_EVALUATION_TIMEOUT_SECONDS
    )


__all__ = ["RunEvaluationController"]
