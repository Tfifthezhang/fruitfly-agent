"""External container evaluation CLI."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import signal
import subprocess

from .catalog import builtin_catalog
from .contracts import EvaluationRequest
from .execution import execute_request


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fruitfly-agent-eval",
        description="standardized, external evaluation consumer for FruitFlyAgent",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    catalog = sub.add_parser("catalog", help="show registered benchmarks")
    catalog.add_argument("--json", action="store_true", help="emit the versioned JSON catalog")
    run = sub.add_parser("run", help="execute an evaluation request")
    run.add_argument("--request", required=True, help="evaluation request JSON")
    run.add_argument("--output-root", help="override .fruitfly/eval")
    run.add_argument("--events", choices=("jsonl",), help="emit stable progress events")
    run.add_argument("--host-config", help="machine-local Eval host YAML")
    for name, help_text in (("prepare", "prepare runtime, tasks and verifier dependencies"),
                            ("check", "check prepared identities without downloads or model calls")):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("--request", required=True)
        command.add_argument("--host-config", help="defaults to workspace .fruitfly/eval-host.yaml")
    stop = sub.add_parser("stop", help="stop one owned evaluation and confirm cleanup")
    stop.add_argument("evaluation_id")
    stop.add_argument("--output-root", default=".fruitfly/eval")
    report = sub.add_parser("report", help="print a stored report")
    report.add_argument("evaluation_id")
    report.add_argument("--output-root", default=".fruitfly/eval")
    report.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "catalog":
            payload = builtin_catalog().to_dict()
            if args.json:
                _print_json(payload)
            else:
                for item in payload["benchmarks"]:
                    variants = ", ".join(
                        f"{variant['id']} ({'ready' if variant['preflight']['available'] else 'unavailable'})"
                        for variant in item["variants"]
                    )
                    print(f"{item['id']:<12} {item['label']} {item['version']}: {variants}")
                    for variant in item["variants"]:
                        if variant["preflight"]["available"]:
                            continue
                        problems = (
                            check["detail"]
                            for check in variant["preflight"]["checks"]
                            if not check["ok"]
                        )
                        for problem in problems:
                            print(f"  {variant['id']}: {problem}")
            return 0
        if args.command == "run":
            request = EvaluationRequest.read(args.request)
            output_root = (
                Path(args.output_root).resolve()
                if args.output_root
                else Path(request.runtime.working_directory).resolve()
                / ".fruitfly"
                / "eval"
            )
            def progress(payload: dict[str, object]) -> None:
                if args.events:
                    _print_json({"schema_version": 1, **payload})

            def interrupt(signum: int, frame: object) -> None:
                raise KeyboardInterrupt("evaluation interrupted")
            previous = signal.signal(signal.SIGTERM, interrupt)
            try:
                report, store = execute_request(
                    request, output_root=output_root, host_config_path=args.host_config,
                    progress=progress if args.events else None,
                )
            finally:
                signal.signal(signal.SIGTERM, previous)
            if args.events:
                _event(
                    "finished",
                    evaluation_id=report.evaluation_id,
                    status=report.status,
                    report_json=str(store.path / "report.json"),
                    report_markdown=str(store.path / "report.md"),
                )
            else:
                print(report.render_markdown(), end="")
                print(f"[report: {store.path / 'report.md'}]")
            return {"completed": 0, "blocked": 3}.get(report.status, 1)
        if args.command in {"prepare", "check"}:
            from .benchmarks.harbor import HarborBenchmarkAdapter
            from .harbor.host import HostConfig
            from .harbor.preparation import inspect, prepare
            from .installation import resolve_installation
            request = EvaluationRequest.read(args.request)
            adapter = builtin_catalog().get(request.benchmark.benchmark_id)
            if not isinstance(adapter, HarborBenchmarkAdapter):
                raise ValueError("preparation commands require a Harbor adapter")
            if request.benchmark.variant not in {v.variant_id for v in adapter.descriptor.variants}:
                raise ValueError("unknown benchmark variant")
            host = HostConfig.read(Path(request.runtime.working_directory).resolve(), args.host_config)
            if args.command == "prepare":
                package = resolve_installation(os.environ.get("FRUITFLY_EVAL_PACKAGE"), checkout=Path(__file__).resolve().parent.parent)
                def interrupt_preparation(signum: int, frame: object) -> None:
                    raise KeyboardInterrupt("preparation interrupted")
                previous = signal.signal(signal.SIGTERM, interrupt_preparation)
                try:
                    payload = prepare(request, adapter.descriptor, host, package=package,
                                      progress=lambda event: print(event["stage"], file=sys.stderr, flush=True))
                finally:
                    signal.signal(signal.SIGTERM, previous)
                _print_json(payload)
                return 0
            payload = inspect(request, adapter.descriptor, host)
            _print_json(payload)
            return 0 if payload["available"] else 3
        if args.command == "stop":
            from .harbor.lifecycle import request_stop
            if Path(args.evaluation_id).name != args.evaluation_id or args.evaluation_id in {".", ".."}:
                raise ValueError("invalid evaluation ID")
            payload = request_stop(Path(args.output_root) / args.evaluation_id)
            _print_json(payload)
            return 0 if payload["state"] == "finished" else 1
        report_path = Path(args.output_root) / args.evaluation_id / "report.json"
        if args.json:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
            _print_json(payload)
        else:
            print(report_path.with_name("report.md").read_text(encoding="utf-8"), end="")
        return 0
    except KeyboardInterrupt:
        print("error: evaluation command interrupted", file=sys.stderr)
        return 130
    except (OSError, TypeError, ValueError, RuntimeError, ImportError, subprocess.SubprocessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _event(event_type: str, **payload: object) -> None:
    _print_json({"schema_version": 1, "type": event_type, **payload})


def _print_json(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), flush=True)


if __name__ == "__main__":
    sys.exit(main())
