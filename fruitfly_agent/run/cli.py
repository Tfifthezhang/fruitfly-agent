"""Thin CLI bootstrap for the interactive-first FruitFlyAgent application."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys

from fruitfly_agent.core.errors import SessionCorruptError
from fruitfly_agent.interactive import AgentApplication, TerminalConfigurationFrontend, TerminalFrontend, TerminalRenderer
from fruitfly_agent.interactive.terminal import transient_screen
from fruitfly_agent.providers.config import load_env
from fruitfly_agent.providers.workspace import WorkspacePaths

from fruitfly_agent.run.application import RunApplicationFactory, resolve_session_path as _resolve_path
from fruitfly_agent.lab.catalog import PermissionPolicy
from fruitfly_agent.providers.registry import default_registry
from fruitfly_agent.run.runtime.limits import ModelCallBudget, BudgetedProviderRegistry


async def run_cli(args: argparse.Namespace) -> int:
    cwd = Path(args.cwd).resolve() if args.cwd else Path.cwd().resolve()
    application: AgentApplication | None = None
    try:
        if args.approve_tools and (not args.task or args.resume):
            raise ValueError("--approve-tools requires a new non-interactive task")
        unrestricted = getattr(args, "unrestricted", False)
        if unrestricted and (not args.task or args.resume or args.approve_tools):
            raise ValueError("--unrestricted requires a fresh non-interactive task and conflicts with --approve-tools")
        paths = WorkspacePaths(cwd)
        for notice in paths.notices():
            print(f"notice: {notice}", file=sys.stderr)
        environment = {**load_env(paths.secret_file()), **os.environ}
        raw_limit = getattr(args, 'max_model_calls', None)
        if raw_limit is None:
            raw_limit = environment.get('FRUITFLY_MAX_MODEL_CALLS')
        registry = None
        if raw_limit is not None:
            if not args.task or args.resume:
                raise ValueError('model request allowance requires a fresh non-interactive task')
            budget = ModelCallBudget(int(raw_limit), receipt=environment.get('FRUITFLY_MODEL_USAGE_PATH'))
            registry = BudgetedProviderRegistry(default_registry(), budget)
        factory = RunApplicationFactory(
            cwd=cwd, environment=environment, config_path=args.config,
            profile_id=args.profile, allow_incomplete=not bool(args.task),
            permission_policy=PermissionPolicy.unrestricted(cwd) if unrestricted else None,
            provider_registry=registry,
        )
        if not args.task:
            with transient_screen(sys.stdin, sys.stdout):
                launch = TerminalConfigurationFrontend(factory.configuration).run(editable=not args.resume)
            if not launch.start:
                return 0
            if launch.saved:
                factory.reload_configuration()

        session_path = resolve_session_path(args, cwd)
        application = AgentApplication(factory)
        if args.approve_tools:
            async def approve_tool(prompt):
                return "once"
            application.set_authorization_handler(approve_tool)
        await application.start(
            resume=bool(args.resume),
            session_path=session_path,
        )
        if args.resume and args.task:
            print(
                f"[resumed {application.status.message_count} messages "
                f"from {session_path}]"
            )
        if args.task:
            renderer = TerminalRenderer(sys.stdout)
            event_stream = None
            event_stream_path = os.environ.get("FRUITFLY_EVENT_STREAM_PATH")
            if event_stream_path:
                event_path = Path(event_stream_path)
                event_path.parent.mkdir(parents=True, exist_ok=True)
                descriptor = os.open(
                    event_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
                )
                event_stream = os.fdopen(descriptor, "w", encoding="utf-8")

            async def render_and_forward(event):
                if event_stream is not None:
                    event_stream.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
                    event_stream.flush()
                await renderer.render(event)

            application.set_event_sink(render_and_forward)
            try:
                result = await application.submit(args.task)
                return 1 if result.is_error else 0
            finally:
                await renderer.close()
                if event_stream is not None:
                    event_stream.close()

        return await TerminalFrontend(application).run()
    except (ValueError, OSError, RuntimeError, SessionCorruptError, TypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        if application is not None:
            try:
                await application.close()
            except Exception as exc:  # cleanup must not crash the CLI process
                print(f"warning: {exc}", file=sys.stderr)


def resolve_session_path(args: argparse.Namespace, cwd: Path) -> Path:
    """Compatibility wrapper around the application factory's path policy."""

    return _resolve_path(
        cwd=cwd,
        session_path=args.session,
        resume=bool(args.resume),
    )


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fruitfly-agent",
        description="interactive-first agent harness",
    )
    parser.add_argument(
        "task",
        nargs="?",
        default="",
        help="task to run; omit it to enter interactive mode",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="resume the latest non-empty session, or select a path with --session",
    )
    parser.add_argument("--approve-tools", action="store_true",
                        help="approve tool confirmation requests for a new task in a trusted isolated environment")
    parser.add_argument("--unrestricted", action="store_true",
                        help="disable application tool permission checks for a fresh task in an externally isolated environment")
    parser.add_argument("--cwd", default=None, help="working directory")
    parser.add_argument('--max-model-calls', type=int, default=None,
                        help='shared main/auxiliary Provider request allowance for a fresh task')
    parser.add_argument(
        "--session",
        default=None,
        help="session jsonl path; new runs otherwise create a timestamped path",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="settings file (defaults to <cwd>/.fruitfly/config.yaml)",
    )
    parser.add_argument(
        "--profile",
        default=None,
        help="named runtime profile from the settings file",
    )
    return parser


def main() -> None:
    args = create_parser().parse_args()
    try:
        sys.exit(asyncio.run(run_cli(args)))
    except KeyboardInterrupt:
        print("\n[interrupted]")
        sys.exit(130)


__all__ = ["create_parser", "resolve_session_path", "run_cli", "main"]
