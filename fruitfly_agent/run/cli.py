"""Thin CLI bootstrap for the interactive-first FruitFlyAgent application."""

from __future__ import annotations

import argparse
import asyncio
from contextlib import nullcontext
import json
import os
from pathlib import Path
import sys

from fruitfly_agent.core.errors import SessionCorruptError
from fruitfly_agent.interactive import AgentApplication, TerminalConfigurationFrontend, TerminalFrontend, TerminalRenderer
from fruitfly_agent.interactive.terminal import transient_screen
from fruitfly_agent.providers.config import load_env
from fruitfly_agent.providers.workspace import WorkspacePaths

from fruitfly_agent.run.extensions import load_extensions
from fruitfly_agent.run.application import RunApplicationFactory, resolve_session_path as _resolve_path
from fruitfly_agent.lab.catalog import PermissionPolicy
from fruitfly_agent.providers.registry import default_registry
from fruitfly_agent.run.runtime.usage import ModelUsage, ObservedProviderRegistry
from fruitfly_agent.core.data_model import TextBlock
from fruitfly_agent.core.data_model.media import UserContent
from fruitfly_agent.interactive.terminal.features.tool_services.approval import approve_start


async def run_cli(args: argparse.Namespace) -> int:
    cwd = Path(args.cwd).resolve() if args.cwd else Path.cwd().resolve()
    application: AgentApplication | None = None
    try:
        images = getattr(args, 'image', None) or []
        single_task = bool(args.task or images)
        configure = getattr(args, 'configure', False)
        if configure and single_task:
            raise ValueError('--configure requires interactive mode; omit the task and --image')
        if args.approve_tools and (not single_task or args.resume):
            raise ValueError("--approve-tools requires a new non-interactive task")
        unrestricted = getattr(args, "unrestricted", False)
        if unrestricted and (not single_task or args.resume or args.approve_tools):
            raise ValueError("--unrestricted requires a fresh non-interactive task and conflicts with --approve-tools")
        paths = WorkspacePaths(cwd)
        environment = {**load_env(paths.secret_file()), **os.environ}
        if 'FRUITFLY_MAX_MODEL_CALLS' in environment:
            raise ValueError('FRUITFLY_MAX_MODEL_CALLS is unsupported; use stage times')
        usage_path=environment.get('FRUITFLY_MODEL_USAGE_PATH')
        registry=ObservedProviderRegistry(default_registry(),ModelUsage(receipt=usage_path)) if usage_path else None
        from fruitfly_agent.runtime_spec import load_harness_config
        config_source = Path(args.config) if args.config else cwd / '.fruitfly/config.yaml'
        if not config_source.is_absolute():
            config_source = cwd / config_source
        try:
            declared = load_harness_config(config_source).select(args.profile).extensions if config_source.is_file() else ()
        except (ValueError, OSError) as exc:
            raise ValueError(str(config_source) + ': ' + str(exc)) from exc
        extensions = load_extensions((*declared, *(getattr(args, 'extension', []) or [])), workspace=cwd)
        factory = RunApplicationFactory(
            cwd=cwd, environment=environment, config_path=args.config,
            profile_id=args.profile, allow_incomplete=not single_task,
            permission_policy=PermissionPolicy.unrestricted(cwd) if unrestricted else None,
            provider_registry=registry,
            tool_service_startup_approval=approve_start,
            extensions=extensions if extensions.registrations else None,
        )
        if not single_task:
            needs_menu = configure or not factory.configuration.snapshot().ready
            scope = transient_screen(sys.stdin, sys.stdout) if needs_menu else nullcontext()
            with scope:
                launch = TerminalConfigurationFrontend(factory.configuration).run(configure=configure)
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
        if args.resume and single_task:
            print(
                f"[resumed {application.status.message_count} messages "
                f"from {session_path}]"
            )
        if single_task:
            content: UserContent = args.task
            if images:
                content = [TextBlock(args.task)] if args.task else []
                content.extend(application.load_attachment(path) for path in images)
            application.validate_input(content)
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
                result = await application.submit(content)
                return 1 if result.is_error else 0
            finally:
                await renderer.close()
                if event_stream is not None:
                    event_stream.close()

        frontend = TerminalFrontend(application)
        if extensions.registrations:
            from fruitfly_agent.run.extensions.commands import bind_extension_commands
            bind_extension_commands(frontend.commands, application, factory)
        return await frontend.run()
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
    parser.add_argument('--extension', action='append', default=[], metavar='SOURCE',
                        help='load a trusted local Python extension or entrypoint:NAME; repeat for multiple sources')
    parser.add_argument(
        "task",
        nargs="?",
        default="",
        help="task to run; omit task and --image to enter interactive mode",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="resume the latest non-empty session, or select a path with --session",
    )
    parser.add_argument('--configure', action='store_true',
                        help='edit configuration before entering interactive chat')
    parser.add_argument("--approve-tools", action="store_true",
                        help="approve tool confirmation requests for a new task in a trusted isolated environment")
    parser.add_argument("--unrestricted", action="store_true",
                        help="disable application tool permission checks for a fresh task in an externally isolated environment")
    parser.add_argument("--cwd", default=None, help="working directory")
    parser.add_argument('--image', action='append', default=[], metavar='PATH',
                        help='attach a local PNG/JPEG/GIF/WebP image; repeat for multiple images; paths resolve from --cwd')
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
