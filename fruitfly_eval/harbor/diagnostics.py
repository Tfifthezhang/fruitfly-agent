"""Phase evidence independent of scores; retain additional typed exceptions."""
from __future__ import annotations

import json
from pathlib import Path
import re
from datetime import datetime
from typing import Any, Mapping
from fruitfly_agent.core.session.observations import read_observation_files, summarize_observations


PHASES = ("environment_setup", "agent_setup", "agent_execution", "verifier")
EXCEPTION_PHASES = {
    "AgentTimeoutError": "agent_execution", "AgentSetupTimeoutError": "agent_setup",
    "VerifierTimeoutError": "verifier", "RewardFileNotFoundError": "verifier",
    "RewardFileEmptyError": "verifier", "EnvironmentBuildTimeoutError": "environment_setup",
    "EnvironmentStartTimeoutError": "environment_setup",
}


def trial_diagnostics(trial: Mapping[str, Any], *, reward: float | None) -> dict[str, Any]:
    errors = []
    exception = trial.get("exception_info")
    if isinstance(exception, Mapping):
        errors.append({"type": exception.get("exception_type"), "message": exception.get("exception_message"),
                       "source": "exception_info"})
    errors.extend(trial.get("_additional_exceptions", []))
    if not isinstance(exception, Mapping) and reward is None:
        errors.insert(0, {"type": "MissingOfficialReward", "message": "no unambiguous official reward was reported",
                          "source": "verifier_result"})
    phases: dict[str, Any] = {}
    for name in PHASES:
        timing = trial.get(name)
        phases[name] = {"state": "unobserved"}
        if isinstance(timing, Mapping):
            phases[name] = {**dict(timing), "state": "ended" if timing.get("finished_at") else "started"}
    fatal = isinstance(exception, Mapping) or reward is None
    for error in errors:
        phase = EXCEPTION_PHASES.get(str(error["type"]).rsplit(".", 1)[-1])
        if phase is not None and (error["source"] == "exception_info" or str(error["type"]).startswith("harbor.trial.errors.")):
            phases[phase]["state"] = "error"
            fatal = True
    for timing_phase in phases.values():
        if timing_phase.get('started_at') and timing_phase.get('finished_at'):
            try:
                timing_phase['elapsed_seconds'] = max(0., (datetime.fromisoformat(str(timing_phase['finished_at']).replace('Z', '+00:00'))
                    - datetime.fromisoformat(str(timing_phase['started_at']).replace('Z', '+00:00'))).total_seconds())
            except ValueError:
                timing_phase['timing_state'] = 'invalid'
    return {"state": "error" if fatal else "completed", "phases": phases, "exceptions": errors,
            "official_reward": reward, "evidence": trial.get("_evidence", []),
            "agent_process": trial.get("_agent_process"),
            "agent_operations": trial.get('_agent_operations', {'collection_state': 'unobserved'}),
            "note": "phase end timestamps alone do not establish success"}


def attach_evidence(trial: dict[str, Any], directory: Path) -> None:
    evidence = []
    additional = []
    seen = set()
    # Only qualified exception summary lines from a Python traceback are parsed.
    # Ordinary text such as 'test failed' is never a cause classifier.
    for name in ("trial.log", "exception.txt"):
        path = directory / name
        if not path.is_file():
            continue
        evidence.append(str(path))
        for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            match = re.fullmatch(r"((?:[A-Za-z_]\w*\.)+[A-Za-z_]\w*(?:Error|Exception)): (.*)", line)
            if match and match.groups() not in seen:
                seen.add(match.groups())
                additional.append({"type": match[1], "message": match[2], "source": str(path), "line": number})
    for root in (directory / "agent", directory / "verifier"):
        if root.is_dir():
            evidence.extend(str(path) for path in sorted(root.glob("*")) if path.is_file())
    process = directory / "agent/process.json"
    if process.is_file():
        try:
            trial["_agent_process"] = json.loads(process.read_text())
        except ValueError:
            trial["_agent_process"] = {"state": "unreadable"}
    trial["_additional_exceptions"] = additional
    trial["_evidence"] = evidence
    session = directory / 'agent/session.jsonl'
    paths = ([session] if session.is_file() and not session.is_symlink() else [])
    paths.extend(path for path in sorted((directory / 'agent/session.jsonl.operations').glob('*.jsonl'))
        if path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(directory.resolve()))
    if paths:
        try:
            trial['_agent_operations'] = {'collection_state': 'collected',
                **summarize_observations(read_observation_files(paths, allow_incomplete=True))}
        except (ValueError, TypeError, OSError):
            trial['_agent_operations'] = {'collection_state': 'collection_failed'}
