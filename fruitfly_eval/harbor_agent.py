"""Harbor installed-agent bridge for the native FruitFlyAgent CLI.

This module is imported by Harbor, not by the FruitFlyAgent production runtime.
Harbor remains the owner of task containers and official verification.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import shlex
import tempfile
import uuid
from typing import Any

from fruitfly_eval.harbor.material import probe_command
from fruitfly_eval.trajectory import session_trajectory


try:  # Harbor is an optional eval dependency.
    from harbor.agents.capabilities import AgentCapabilities
    from harbor.agents.installed.base import BaseInstalledAgent, with_prompt_template
    from harbor.environments.base import BaseEnvironment
    from harbor.models.agent.context import AgentContext
except ImportError:  # pragma: no cover - exercised by catalog preflight instead
    AgentCapabilities = None  # type: ignore[assignment,misc]
    BaseInstalledAgent = object  # type: ignore[assignment,misc]
    BaseEnvironment = Any  # type: ignore[assignment,misc]
    AgentContext = Any  # type: ignore[assignment,misc]

    def with_prompt_template(function):  # type: ignore[no-untyped-def]
        return function


class FruitFlyHarborAgent(BaseInstalledAgent):  # type: ignore[misc]
    """Validate a prepared, mounted runtime and run the native CLI inside Harbor."""

    if AgentCapabilities is not None:
        capabilities = AgentCapabilities(atif=True)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.config_path = Path(_required(kwargs.pop("config_path", None), "config_path"))
        self.model_catalog_path = Path(
            _required(kwargs.pop("model_catalog_path", None), "model_catalog_path")
        )
        self.profile = _required(kwargs.pop("profile", None), "profile")
        names = str(kwargs.pop("secret_names", ""))
        inherited = dict(kwargs.pop("extra_env", None) or {})
        for name in filter(None, (item.strip() for item in names.split(","))):
            if name in os.environ:
                inherited[name] = os.environ[name]
        kwargs["extra_env"] = inherited
        super().__init__(*args, **kwargs)

    @staticmethod
    def name() -> str:
        return "fruitfly-agent"

    def version(self) -> str | None:
        return "0.1"

    async def install(self, environment: BaseEnvironment) -> None:
        preparation = self.config_path.parent / "preparation.json"
        if not preparation.is_file():
            raise ValueError("prepared runtime receipt is missing; run eval prepare before evaluation")
        self.preparation = json.loads(preparation.read_text(encoding="utf-8"))
        runtime = self.preparation["runtime"]
        self.runtime_python = runtime["python"]
        self.runtime_environment = runtime["environment"]
        for path in (self.config_path, self.model_catalog_path):
            if not path.is_file():
                raise ValueError(f"installation runtime file is missing: {path}")
        await self.exec_as_agent(environment, command=shlex.join(probe_command(self.runtime_python)),
                                 env=self.runtime_environment, timeout_sec=60)
        await self.exec_as_root(environment, command="mkdir -p /installed-agent/fruitfly/runtime")
        for source, target in ((self.config_path, "config.yaml"), (self.model_catalog_path, "models.yaml")):
            await environment.upload_file(source, "/installed-agent/fruitfly/runtime/" + target)
        receipt = self.config_path.parent / "runtime.json"
        if receipt.is_file():
            await environment.upload_file(receipt, "/installed-agent/fruitfly/runtime/runtime.json")
            await environment.upload_file(receipt, "/logs/agent/runtime.json")
        artifacts = self.config_path.parent / "artifacts"
        if artifacts.is_dir():
            await environment.upload_dir(artifacts, "/installed-agent/fruitfly/runtime/artifacts")
        with tempfile.TemporaryDirectory(prefix="fruitfly-identity-") as directory:
            identity = Path(directory) / "installation.json"
            identity.write_text(json.dumps(runtime["installation"], indent=2) + "\n", encoding="utf-8")
            await environment.upload_file(identity, "/logs/agent/installation.json")
        await environment.upload_file(preparation, "/logs/agent/preparation.json")

    async def _exec(
        self, environment: BaseEnvironment, command: str,
        user: str | int | None = None, env: dict[str, str] | None = None,
        cwd: str | None = None, timeout_sec: int | None = None,
    ) -> Any:
        # Root commands are installation only. Tee inside the container so even
        # a cancelled/expired environment.exec leaves its partial output visible.
        if user == "root":
            label = shlex.quote("[setup] " + self._redact_command(command))
            command = (
                "set -o pipefail; mkdir -p /logs/agent && "
                "{ printf '%s\\n' " + label + "; " + command
                + "; } 2>&1 | tee -a /logs/agent/setup.log"
            )
        return await super()._exec(
            environment, command, user=user, env=env, cwd=cwd,
            timeout_sec=timeout_sec,
        )

    @with_prompt_template
    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        token = uuid.uuid4().hex
        command = shlex.join(
            [
                self.runtime_python,
                "-P", "-m", "fruitfly_eval.harbor.supervisor", "--record", "/logs/agent/process.json", "--token", token, "--",
                self.runtime_python,
                "-P",
                "-m",
                "fruitfly_agent",
                "--unrestricted",
                "--cwd",
                ".",
                "--config",
                "/installed-agent/fruitfly/runtime/config.yaml",
                "--profile",
                self.profile,
                "--session",
                "/logs/agent/session.jsonl",
                "--",
                instruction,
            ]
        )
        command = (
            "if [ -d /installed-agent/fruitfly/runtime/artifacts ]; then "
            "mkdir -p .fruitfly/artifacts && "
            "cp -n /installed-agent/fruitfly/runtime/artifacts/* .fruitfly/artifacts/; "
            "fi && " + command
        )
        # Supervise the real CLI rather than just the docker-exec client. An
        # expired Harbor await must not leave an Agent making requests behind.
        env = {**self.runtime_environment, **self.preparation["runtime"]["host"].get("agent", {}),
               "FRUITFLY_EVENT_STREAM_PATH": "/logs/agent/live-events.jsonl"}
        env['FRUITFLY_MODEL_USAGE_PATH'] = '/logs/agent/model-usage.json'
        try:
            await self.exec_as_agent(environment, command=command, env=env)
        except BaseException as primary:
            cleanup = asyncio.create_task(self.exec_as_agent(environment, command=shlex.join([
                self.runtime_python, "-P", "-m", "fruitfly_eval.harbor.supervisor", "--record", "/logs/agent/process.json", "--token", token, "--stop",
            ]), env=self.runtime_environment, timeout_sec=12))
            try:
                await asyncio.wait_for(asyncio.shield(cleanup), timeout=15)
            except BaseException as cleanup_error:
                cleanup.cancel()
                await asyncio.gather(cleanup, return_exceptions=True)
                # Failed control cleanup forbids verification against an Agent
                # that is still changing files. Harbor retains the trial logs.
                stopped = True
                stop_type = None
                try:
                    await asyncio.wait_for(environment.stop(delete=False), timeout=15)
                except BaseException as stop_error:
                    stopped = False
                    stop_type = type(stop_error).__name__
                failure = RuntimeError('Agent cancellation cleanup failed; environment ' + ('stopped' if stopped else 'stop unconfirmed'))
                if stop_type:
                    failure.add_note('Environment stop failure type: ' + stop_type)
                failure.add_note('Primary failure type: ' + type(primary).__name__)
                failure.add_note('Cleanup failure type: ' + type(cleanup_error).__name__)
                raise failure from primary
            raise

    def populate_context_post_run(self, context: AgentContext) -> None:
        session_path = self.logs_dir / "session.jsonl"
        if not session_path.is_file():
            return
        metadata = dict(context.metadata or {})
        metadata.update({"harness": "fruitfly-agent", "native_tools_preserved": True})
        context.metadata = metadata
        context.n_input_tokens = context.n_output_tokens = None
        try:
            installation = self.logs_dir / "installation.json"
            if installation.is_file():
                metadata["installation"] = json.loads(installation.read_text(encoding="utf-8"))
            receipt = self.logs_dir / "runtime.json"
            if receipt.is_file():
                metadata["runtime_snapshot"] = json.loads(receipt.read_text(encoding="utf-8"))
            trajectory = session_trajectory(session_path, version=self.version() or "0.1")
            (self.logs_dir / "trajectory.json").write_text(
                json.dumps(trajectory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            manifest = trajectory["extra"]["runtime_manifest"]
            if manifest:
                metadata["runtime_manifest"] = manifest
                metadata["runtime_manifest_digest"] = manifest.get("digest")
            metrics = trajectory["final_metrics"]
            context.n_input_tokens = metrics.get("total_prompt_tokens")
            context.n_output_tokens = metrics.get("total_completion_tokens")
        except (OSError, TypeError, ValueError, KeyError) as exc:
            metadata["trajectory_error"] = str(exc)


def _required(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"FruitFly Harbor agent requires {name}")
    return value


__all__ = ["FruitFlyHarborAgent"]
