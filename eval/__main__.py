"""Stable CLI used by the TUI and external automation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .catalog import builtin_catalog
from .contracts import EvaluationRequest
from .execution import execute_plan
from .planning import create_plan


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fruitfly-agent-eval",
        description="standardized, external evaluation consumer for FruitFlyAgent",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    catalog = sub.add_parser("catalog", help="show registered modes and benchmarks")
    catalog.add_argument("--json", action="store_true", help="emit the versioned JSON catalog")
    plan = sub.add_parser("plan", help="validate a request and freeze an execution plan")
    plan.add_argument("--request", required=True, help="evaluation request JSON")
    plan.add_argument("--output", help="write the plan to this path")
    run = sub.add_parser("run", help="plan and execute an evaluation request")
    run.add_argument("--request", required=True, help="evaluation request JSON")
    run.add_argument("--output-root", help="override .fruitfly/eval")
    run.add_argument("--events", choices=("jsonl",), help="emit stable progress events")
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
        if args.command == "plan":
            request = EvaluationRequest.read(args.request)
            plan = create_plan(request)
            payload = plan.to_dict()
            if args.output:
                Path(args.output).write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
            else:
                _print_json(payload)
            return 0
        if args.command == "run":
            request = EvaluationRequest.read(args.request)
            plan = create_plan(request)
            if args.events:
                _event("planned", evaluation_id=plan.evaluation_id)
            output_root = (
                Path(args.output_root).resolve()
                if args.output_root
                else Path(request.runtime.working_directory).resolve()
                / ".fruitfly"
                / "eval"
            )
            def progress(payload: dict[str, object]) -> None:
                if args.events:
                    _print_json({"schema_version": 1, "evaluation_id": plan.evaluation_id, **payload})

            report, store = execute_plan(
                plan, output_root=output_root,
                progress=progress if args.events else None,
            )
            if args.events:
                _event(
                    "finished",
                    evaluation_id=plan.evaluation_id,
                    status=report.status,
                    report_json=str(store.path / "report.json"),
                    report_markdown=str(store.path / "report.md"),
                )
            else:
                print(report.render_markdown(), end="")
                print(f"[report: {store.path / 'report.md'}]")
            return {"completed": 0, "blocked": 3}.get(report.status, 1)
        report_path = Path(args.output_root) / args.evaluation_id / "report.json"
        if args.json:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
            _print_json(payload)
        else:
            print(report_path.with_name("report.md").read_text(encoding="utf-8"), end="")
        return 0
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _event(event_type: str, **payload: object) -> None:
    _print_json({"schema_version": 1, "type": event_type, **payload})


def _print_json(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), flush=True)


if __name__ == "__main__":
    sys.exit(main())
