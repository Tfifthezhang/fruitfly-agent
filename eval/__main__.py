"""Stable CLI used by the TUI and external automation."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

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
    catalog.add_argument("--improvement", action="store_true", help="show bounded task sources for improvement")
    run = sub.add_parser("run", help="execute an evaluation request")
    run.add_argument("--request", required=True, help="evaluation request JSON")
    run.add_argument("--output-root", help="override .fruitfly/eval")
    run.add_argument("--events", choices=("jsonl",), help="emit stable progress events")
    report = sub.add_parser("report", help="print a stored report")
    report.add_argument("evaluation_id")
    report.add_argument("--output-root", default=".fruitfly/eval")
    report.add_argument("--json", action="store_true")
    trial = sub.add_parser("trial", help="run one original task with an isolated versioned runtime")
    trial.add_argument("--request", required=True)
    trial.add_argument("--output-root", required=True)
    trial.add_argument("--events", choices=("jsonl",))
    prepare = sub.add_parser("prepare", help="download and freeze official tasks without executing an Agent")
    prepare.add_argument("--benchmark", required=True)
    prepare.add_argument("--variant", required=True)
    prepare.add_argument("--task-limit", type=int, default=5)
    prepare.add_argument("--output-root", required=True)
    prepare.add_argument("--events", choices=("jsonl",))
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "catalog":
            payload = builtin_catalog().to_dict()
            if args.improvement:
                from .task_sets import improvement_catalog
                payload = improvement_catalog(builtin_catalog())
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

            report, store = execute_request(
                request, output_root=output_root,
                progress=progress if args.events else None,
            )
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
        if args.command == "trial":
            from .trial import run_trial
            def trial_progress(payload):
                if args.events:
                    _print_json({"schema_version": 1, **payload})
            payload = run_trial(json.loads(Path(args.request).read_text(encoding="utf-8")),
                output_root=Path(args.output_root), progress=trial_progress)
            _print_json({"type": "trial-result", **payload})
            return 0
        if args.command == "prepare":
            from .task_sets import prepare_task_set
            payload = asyncio.run(prepare_task_set(args.benchmark, args.variant, args.task_limit,
                output_root=Path(args.output_root),
                progress=lambda row: _print_json({"schema_version": 1, **row}) if args.events else None))
            _print_json({"type": "task-set-prepared", **payload})
            return 0
        report_path = Path(args.output_root) / args.evaluation_id / "report.json"
        if args.json:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
            _print_json(payload)
        else:
            print(report_path.with_name("report.md").read_text(encoding="utf-8"), end="")
        return 0
    except (OSError, TypeError, ValueError, RuntimeError, ImportError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _event(event_type: str, **payload: object) -> None:
    _print_json({"schema_version": 1, "type": event_type, **payload})


def _print_json(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), flush=True)


if __name__ == "__main__":
    sys.exit(main())
