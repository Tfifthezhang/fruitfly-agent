"""Harbor installed-agent bridge for the native FruitFlyAgent CLI.

This module is imported by Harbor, not by the FruitFlyAgent production runtime.
Harbor remains the owner of task containers and official verification.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
from typing import Any


try:  # Harbor is an optional eval dependency.
    from harbor.agents.installed.base import BaseInstalledAgent, with_prompt_template
    from harbor.environments.base import BaseEnvironment
    from harbor.models.agent.context import AgentContext
except ImportError:  # pragma: no cover - exercised by catalog preflight instead
    BaseInstalledAgent = object  # type: ignore[assignment,misc]
    BaseEnvironment = Any  # type: ignore[assignment,misc]
    AgentContext = Any  # type: ignore[assignment,misc]

    def with_prompt_template(function):  # type: ignore[no-untyped-def]
        return function


class FruitFlyHarborAgent(BaseInstalledAgent):  # type: ignore[misc]
    """Install the current source snapshot, then run its unmodified one-shot CLI."""

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
        await environment.upload_dir(
            self.source_root / "fruitfly_agent",
            "/installed-agent/fruitfly/source/fruitfly_agent",
        )
        await environment.upload_file(
            self.source_root / "pyproject.toml",
            "/installed-agent/fruitfly/source/pyproject.toml",
        )
        await environment.upload_file(
            self.source_root / "LICENSE",
            "/installed-agent/fruitfly/source/LICENSE",
        )
        await environment.upload_file(
            self.config_path,
            "/installed-agent/fruitfly/runtime/config.yaml",
        )
        await environment.upload_file(
            self.model_catalog_path,
            "/installed-agent/fruitfly/runtime/models.yaml",
        )
        if use_existing_python:
            command = (
                "python3 -m venv /installed-agent/fruitfly/venv && "
                "/installed-agent/fruitfly/venv/bin/python -m pip install "
                "--disable-pip-version-check --timeout 15 --retries 1 "
                "/installed-agent/fruitfly/source"
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
                "/installed-agent/fruitfly/source"
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
                "mkdir -p /logs/agent && "
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
                "--cwd",
                ".",
                "--config",
                "/installed-agent/fruitfly/runtime/config.yaml",
                "--profile",
                shlex.quote(self.profile),
                "--session",
                "/logs/agent/session.jsonl",
                shlex.quote(instruction),
            )
        )
        await self.exec_as_agent(environment, command=command)

    def populate_context_post_run(self, context: AgentContext) -> None:
        session_path = self.logs_dir / "session.jsonl"
        if not session_path.is_file():
            return
        input_tokens = 0
        output_tokens = 0
        digest = None
        try:
            for line in session_path.read_text(encoding="utf-8").splitlines():
                entry = json.loads(line)
                if (
                    entry.get("type") == "meta"
                    and entry.get("kind") == "runtimeManifest"
                    and isinstance(entry.get("manifest"), dict)
                ):
                    digest = entry["manifest"].get("digest")
                message = entry.get("message", {})
                usage = message.get("usage", {}) if isinstance(message, dict) else {}
                input_tokens += _usage_int(usage, "inputTokens", "input_tokens")
                output_tokens += _usage_int(usage, "outputTokens", "output_tokens")
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return
        metadata = dict(context.metadata or {})
        metadata.update({"harness": "fruitfly-agent", "native_tools_preserved": True})
        if isinstance(digest, str):
            metadata["runtime_manifest_digest"] = digest
        context.metadata = metadata
        context.n_input_tokens = input_tokens or None
        context.n_output_tokens = output_tokens or None


def _required(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"FruitFly Harbor agent requires {name}")
    return value


def _usage_int(usage: Any, *names: str) -> int:
    if not isinstance(usage, dict):
        return 0
    for name in names:
        value = usage.get(name)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return 0


__all__ = ["FruitFlyHarborAgent"]
