"""Real-model smoke checks for any provider registered in FruitFlyAgent.

This module makes paid network requests and is intentionally excluded from
the offline unittest suite.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Awaitable, Callable

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.lab.environment import LocalEnv
from fruitfly_agent.core.extensions.hooks import HookRegistry
from fruitfly_agent.core.loop import run_agent_loop
from fruitfly_agent.core.session import Session
from fruitfly_agent.lab.context_manager.reduction import (
    SummarizingCompactor,
    SummarizingCompactorConfig,
)
from fruitfly_agent.lab.tools import builtin_tools
from fruitfly_agent.core.data_model import AgentLoopResult, UserMessage
from fruitfly_agent.providers.config import load_env
from fruitfly_agent.providers.registry import default_registry, load_model_specs
from fruitfly_agent.providers.specs import ModelSpec


@dataclass(frozen=True)
class SmokeOutcome:
    scenario: str
    passed: bool
    provider: str
    model: str
    model_profile: str
    duration_s: float
    turn_count: int = 0
    tool_call_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    compactions: int = 0
    error: str | None = None


def _provider(spec: ModelSpec, env: dict[str, str], *, max_tokens: int | None = None):
    chosen = replace(spec, max_output_tokens=max_tokens or spec.max_output_tokens)
    return default_registry().create(chosen, env)


def _config(
    spec: ModelSpec, env: dict[str, str], work: Path, session: Session, **changes
) -> AgentLoopConfig:
    config = AgentLoopConfig(
        provider=_provider(spec, env),
        model=spec.model,
        max_tokens=spec.max_output_tokens,
        system_prompt="You are a coding agent. Use tools, act, and be concise.",
        context_window=spec.context_window,
        tools=builtin_tools(),
        env=LocalEnv(cwd=str(work)),
        session=session,
        hooks=HookRegistry(session=session),
    )
    return replace(config, **changes)


def _outcome(
    scenario: str,
    spec: ModelSpec,
    result: AgentLoopResult,
    started: float,
    *,
    passed: bool,
    compactions: int = 0,
) -> SmokeOutcome:
    return SmokeOutcome(
        scenario=scenario,
        passed=passed,
        provider=spec.provider.type,
        model=spec.model,
        model_profile=spec.id,
        duration_s=time.monotonic() - started,
        turn_count=result.turn_count,
        tool_call_count=result.tool_call_count,
        input_tokens=result.usage.input_tokens,
        output_tokens=result.usage.output_tokens,
        compactions=compactions,
        error=str(result.error_details) if result.is_error else None,
    )


async def scenario_1(spec: ModelSpec, env: dict[str, str], root: Path) -> SmokeOutcome:
    """Tool-use happy path."""
    started = time.monotonic()
    work = root / "happy-path"
    work.mkdir(parents=True, exist_ok=True)
    session = Session(work / "session.jsonl")
    try:
        config = _config(spec, env, work, session)
        result = await run_agent_loop(config, [UserMessage(
            content="Write hello.py that prints 'hello from FruitFlyAgent', run it, and report its output."
        )])
        passed = not result.is_error and any(
            "hello from FruitFlyAgent" in getattr(message, "text", "")
            for message in reversed(result.messages)
        )
        return _outcome("happy_path", spec, result, started, passed=passed)
    finally:
        session.close()


async def scenario_2(spec: ModelSpec, env: dict[str, str], root: Path) -> SmokeOutcome:
    """Long-context path with the compaction ladder enabled."""
    started = time.monotonic()
    work = root / "context-pressure"
    work.mkdir(parents=True, exist_ok=True)
    (work / "big.txt").write_text(
        "".join(f"line {i}: {'x' * 80}\n" for i in range(4000)), encoding="utf-8"
    )
    session = Session(work / "session.jsonl")
    window = min(spec.context_window, 64_000)
    try:
        config = _config(spec, env, work, session, context_window=window)
        compaction = SummarizingCompactorConfig(
            reserve_tokens=min(8_000, window // 4),
            keep_recent_tokens=min(12_000, window // 3),
        )
        compactor = SummarizingCompactor(
            compaction, _provider(spec, env, max_tokens=2048)
        )
        result = await run_agent_loop(config, [UserMessage(content=(
            "Read big.txt in full, paging when needed, then report the total line count "
            "and the content of line 3999."
        ))], context_pipeline=compactor)
        compactions = sum(1 for entry in session.read_all() if entry.type == "compaction")
        passed = not result.is_error and compactions >= 1 and any(
            "4000" in getattr(message, "text", "") for message in reversed(result.messages)
        )
        return _outcome(
            "context_pressure", spec, result, started, passed=passed, compactions=compactions
        )
    finally:
        session.close()


async def scenario_3(spec: ModelSpec, env: dict[str, str], root: Path) -> SmokeOutcome:
    """Replay scenario 1's real session and continue from it."""
    started = time.monotonic()
    work = root / "happy-path"
    session = Session(work / "session.jsonl")
    try:
        history = session.messages()
        if not history:
            raise RuntimeError("scenario 3 needs scenario 1 history; run all or scenario 1 first")
        config = _config(spec, env, work, session)
        result = await run_agent_loop(config, [
            *history,
            UserMessage(content="Now make hello.py print a second line containing 'resume works'."),
        ])
        passed = not result.is_error and (work / "hello.py").is_file()
        return _outcome("session_resume", spec, result, started, passed=passed)
    finally:
        session.close()


SCENARIOS: dict[str, Callable[[ModelSpec, dict[str, str], Path], Awaitable[SmokeOutcome]]] = {
    "1": scenario_1,
    "2": scenario_2,
    "3": scenario_3,
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="paid real-provider smoke tests")
    parser.add_argument("--models-file", required=True)
    parser.add_argument("--model-profile", required=True)
    parser.add_argument("--scenario", choices=tuple(SCENARIOS), action="append")
    parser.add_argument("--workdir", default=".fruitfly/smoke")
    parser.add_argument("--json", dest="json_path")
    return parser


async def _run(args: argparse.Namespace) -> int:
    catalog = load_model_specs(args.models_file)
    if args.model_profile not in catalog:
        raise ValueError(f"unknown model profile: {args.model_profile!r}")
    spec = catalog[args.model_profile]
    spec.require(tools=True, streaming=True)
    env = {**os.environ, **load_env()}
    # Fail before creating workspaces or making a paid request.
    default_registry().create(spec, env)
    safe_profile = re.sub(r"[^a-zA-Z0-9_.-]+", "-", spec.id)
    root = Path(args.workdir).resolve() / safe_profile
    root.mkdir(parents=True, exist_ok=True)

    outcomes: list[SmokeOutcome] = []
    for name in args.scenario or ("1", "2", "3"):
        try:
            outcome = await SCENARIOS[name](spec, env, root)
        except Exception as exc:  # noqa: BLE001
            outcome = SmokeOutcome(
                scenario=name,
                passed=False,
                provider=spec.provider.type,
                model=spec.model,
                model_profile=spec.id,
                duration_s=0.0,
                error=f"{type(exc).__name__}: {exc}",
            )
        outcomes.append(outcome)
        print(f"{'PASS' if outcome.passed else 'FAIL'} {outcome.scenario} "
              f"{outcome.duration_s:.2f}s model={outcome.model}")

    payload = {
        "kind": "integration-smoke",
        "model_profile": spec.id,
        "provider": spec.provider.type,
        "model": spec.model,
        "outcomes": [asdict(outcome) for outcome in outcomes],
    }
    if args.json_path:
        Path(args.json_path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return 0 if all(outcome.passed for outcome in outcomes) else 1


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return asyncio.run(_run(args))
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
