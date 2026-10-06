"""Thin CLI bootstrap for the interactive-first FruitFlyAgent application."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys

from fruitfly_agent.core.errors import SessionCorruptError
from fruitfly_agent.interactive import (
    AgentApplication,
    TerminalConfigurationFrontend,
    TerminalFrontend,
    TerminalRenderer,
)
from fruitfly_agent.interactive.terminal import transient_screen
from fruitfly_agent.providers.config import load_env

from .application import RunApplicationFactory, resolve_session_path as _resolve_path
from .evaluation import RunEvaluationController


async def run_cli(args: argparse.Namespace) -> int:
    environment = {**os.environ, **load_env()}
    cwd = Path(args.cwd).resolve() if args.cwd else Path.cwd().resolve()
    application: AgentApplication | None = None
    try:
        factory = RunApplicationFactory(
            cwd=cwd,
            environment=environment,
            config_path=args.config,
            profile_id=args.profile,
            allow_incomplete=not bool(args.task),
        )
        if not args.task:
            with transient_screen(sys.stdin, sys.stdout):
                launch = TerminalConfigurationFrontend(factory.configuration).run(
                    editable=not args.resume
                )
            if not launch.start:
                return 0
            if launch.saved:
                factory.reload_configuration()

        session_path = resolve_session_path(args, cwd)
        application = AgentApplication(factory)
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

        return await TerminalFrontend(
            application,
            evaluation=RunEvaluationController(application, factory),
        ).run()
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
        help="load the specified or latest non-empty session",
    )
    parser.add_argument("--cwd", default=None, help="working directory")
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
