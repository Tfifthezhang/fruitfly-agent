"""Harbor installed-agent bridge for the native FruitFlyAgent CLI.

This module is imported by Harbor, not by the FruitFlyAgent production runtime.
Harbor remains the owner of task containers and official verification.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import shutil
import tempfile
from typing import Any

from eval.installation import SOURCE_FILES, SOURCE_PACKAGES, installation_identity, validate_installation
from eval.trajectory import session_trajectory


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
    """Install validated source or a wheel, then run its normal one-shot CLI."""

    if AgentCapabilities is not None:
        capabilities = AgentCapabilities(atif=True)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.source_root = Path(_required(kwargs.pop("source_root", None), "source_root"))
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
        package = validate_installation(self.source_root)
        for path in (self.config_path, self.model_catalog_path):
            if not path.is_file():
                raise ValueError(f"installation runtime file is missing: {path}")
        identity = installation_identity(package)
        # Official task images may already provide a suitable Python. Avoid an
        # unnecessary apt update and a second Python/uv download in that case.
        probe = await environment.exec(
            command="python3 -c 'import sys, venv; assert sys.version_info >= (3, 11)'",
            user="root", timeout_sec=15,
        )
        use_existing_python = probe.return_code == 0
        if not use_existing_python:
            await self.ensure_system_dependencies(
                environment, ("curl", "ca_certificates", "bash", "git")
            )
        await self.exec_as_root(
            environment,
            command="mkdir -p /installed-agent/fruitfly/source /installed-agent/fruitfly/runtime",
        )
        install_target = "/installed-agent/fruitfly/source"
        if package.is_file():
            install_target += "/" + package.name
            await environment.upload_file(package, install_target)
        else:
            # Stage only package code and declared build inputs, never local state.
            with tempfile.TemporaryDirectory(prefix="fruitfly-install-") as directory:
                staged = Path(directory)
                for name in SOURCE_PACKAGES:
                    for source in (package / name).rglob("*.py"):
                        if "__pycache__" in source.parts or source.is_symlink():
                            continue
                        target = staged / source.relative_to(package)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(source, target)
                for name in SOURCE_FILES:
                    shutil.copyfile(package / name, staged / name)
                identity = installation_identity(staged)
                await environment.upload_dir(staged, install_target)
        await environment.upload_file(
            self.config_path,
            "/installed-agent/fruitfly/runtime/config.yaml",
        )
        await environment.upload_file(
            self.model_catalog_path,
            "/installed-agent/fruitfly/runtime/models.yaml",
        )
        receipt = self.config_path.parent / "runtime.json"
        if receipt.is_file():
            await environment.upload_file(receipt, "/installed-agent/fruitfly/runtime/runtime.json")
            await environment.upload_file(receipt, "/logs/agent/runtime.json")
        artifacts = self.config_path.parent / "artifacts"
        if artifacts.is_dir():
            await environment.upload_dir(artifacts, "/installed-agent/fruitfly/runtime/artifacts")
        with tempfile.TemporaryDirectory(prefix="fruitfly-identity-") as directory:
            receipt = Path(directory) / "installation.json"
            receipt.write_text(json.dumps(identity, indent=2) + "\n", encoding="utf-8")
            await environment.upload_file(receipt, "/logs/agent/installation.json")
        if use_existing_python:
            command = (
                "python3 -m venv /installed-agent/fruitfly/venv && "
                "/installed-agent/fruitfly/venv/bin/python -m pip install "
                "--disable-pip-version-check --timeout 15 --retries 1 "
                + shlex.quote(install_target)
            )
        else:
            command = (
                "curl --connect-timeout 15 --max-time 60 -LsSf "
                "https://astral.sh/uv/0.8.22/install.sh "
                "-o /installed-agent/fruitfly/install-uv.sh && "
                "env UV_INSTALL_DIR=/installed-agent/fruitfly/bin "
                "sh /installed-agent/fruitfly/install-uv.sh && "
                "/installed-agent/fruitfly/bin/uv venv --python 3.12 "
                "/installed-agent/fruitfly/venv && "
                "/installed-agent/fruitfly/bin/uv pip install --python "
                "/installed-agent/fruitfly/venv/bin/python "
                + shlex.quote(install_target)
            )
        await self.exec_as_root(environment, command=command, timeout_sec=300)

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
        command = " ".join(
            (
                "FRUITFLY_EVENT_STREAM_PATH=/logs/agent/live-events.jsonl",
                "/installed-agent/fruitfly/venv/bin/python",
                "-m",
                "fruitfly_agent",
                "--unrestricted",
                "--cwd",
                ".",
                "--config",
                "/installed-agent/fruitfly/runtime/config.yaml",
                "--profile",
                shlex.quote(self.profile),
                "--session",
                "/logs/agent/session.jsonl",
                "--",
                shlex.quote(instruction),
            )
        )
        command = (
            "if [ -d /installed-agent/fruitfly/runtime/artifacts ]; then "
            "mkdir -p .fruitfly/artifacts && "
            "cp -n /installed-agent/fruitfly/runtime/artifacts/* .fruitfly/artifacts/; "
            "fi && " + command
        )
        await self.exec_as_agent(environment, command=command)

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
