"""Parse official Harbor rewards, failures and available measurements."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


def load_harbor_job_result(path: Path) -> Mapping[str, Any]:
    """Load Harbor's job summary and its separately stored trial results."""
    result = dict(_load_object(path))
    embedded = result.get("trial_results")
    if embedded:
        return result
    trial_paths = sorted(path.parent.glob("*/result.json"))
    expected = result.get("n_total_trials")
    if (
        isinstance(expected, int)
        and not isinstance(expected, bool)
        and expected > len(trial_paths)
    ):
        raise ValueError(
            f"Harbor job has {len(trial_paths)} of {expected} trial result files"
        )
    result["trial_results"] = [_load_object(trial_path) for trial_path in trial_paths]
    return result


def parse_harbor_job_result(
    data: Mapping[str, Any],
    *,
    job_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    raw_trials = data.get("trial_results", [])
    if not isinstance(raw_trials, list):
        raise ValueError("Harbor result trial_results must be a list")
    if not raw_trials:
        raise ValueError("Harbor result contains no trials")
    trials: list[dict[str, Any]] = []
    rewards: list[float] = []
    errors = 0
    timeouts = 0
    input_tokens = 0
    output_tokens = 0
    costs = 0.0
    usage_samples = 0
    cost_samples = 0
    latencies: list[float] = []
    for index, raw in enumerate(raw_trials):
        trial = _mapping(raw, "Harbor trial")
        exception = trial.get("exception_info")
        reward = _official_reward(trial)
        agent_result = trial.get("agent_result")
        status, error, timed_out = _trial_status(exception, reward)
        errors += int(error is not None)
        timeouts += int(timed_out)
        if error is None and reward is not None:
            rewards.append(reward)
        if isinstance(agent_result, Mapping):
            raw_input = agent_result.get("n_input_tokens")
            raw_output = agent_result.get("n_output_tokens")
            if _is_integer(raw_input) or _is_integer(raw_output):
                usage_samples += 1
                input_tokens += _integer(raw_input)
                output_tokens += _integer(raw_output)
            raw_cost = agent_result.get("cost_usd")
            if isinstance(raw_cost, (int, float)) and not isinstance(raw_cost, bool):
                cost_samples += 1
                costs += _number(raw_cost)
        latency_ms = _duration_ms(trial.get("agent_execution"))
        if latency_ms is not None:
            latencies.append(latency_ms)
        task_id = str(trial.get("task_name") or trial.get("trial_name") or index)
        metrics = (
            []
            if reward is None or error is not None
            else [{"name": "official_reward", "value": reward}]
        )
        trials.append(
            {
                "trial_id": str(trial.get("id") or f"{job_id}-{index}"),
                "task_id": task_id,
                "status": status,
                "metrics": metrics,
                "error": error,
                "runtime": _runtime_metadata(agent_result),
            }
        )
    count = len(raw_trials)
    success_count = sum(item["status"] == "passed" for item in trials)
    values = {
        "success_rate": success_count / count if count else None,
        "official_reward": sum(rewards) / len(rewards) if rewards else None,
        "error_rate": errors / count if count else None,
        "timeout_rate": timeouts / count if count else None,
        "input_tokens": input_tokens if usage_samples else None,
        "output_tokens": output_tokens if usage_samples else None,
        "cost_usd": costs if cost_samples else None,
        "latency_ms": sum(latencies) / len(latencies) if latencies else None,
    }
    return trials, _benchmark_metrics(values, count)


def _official_reward(trial: Mapping[str, Any]) -> float | None:
    verifier = trial.get("verifier_result")
    raw_rewards = verifier.get("rewards") if isinstance(verifier, Mapping) else None
    reward_map = raw_rewards if isinstance(raw_rewards, Mapping) else {}
    numeric_rewards = [
        float(value) for value in reward_map.values()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    ]
    return (
        float(reward_map["reward"])
        if isinstance(reward_map.get("reward"), (int, float))
        else (numeric_rewards[0] if len(numeric_rewards) == 1 else None)
    )


def _runtime_metadata(agent_result: object) -> dict | None:
    metadata = agent_result.get("metadata") if isinstance(agent_result, Mapping) else None
    manifest = metadata.get("runtime_manifest") if isinstance(metadata, Mapping) else None
    return dict(manifest) if isinstance(manifest, Mapping) else None


def _trial_status(exception: object, reward: float | None) -> tuple[str, dict[str, str] | None, bool]:
    if isinstance(exception, Mapping):
        kind = str(exception.get("exception_type", ""))
        return "error", {"type": kind or "HarborTrialError", "message": str(exception.get("exception_message", ""))}, "timeout" in kind.lower()
    return ("passed" if reward is not None and reward >= 1.0 else "failed"), None, False


def _benchmark_metrics(
    values: Mapping[str, int | float | None], count: int,
) -> list[dict[str, Any]]:
    units = {
        "success_rate": "ratio",
        "official_reward": "score",
        "error_rate": "ratio",
        "timeout_rate": "ratio",
        "input_tokens": "tokens",
        "output_tokens": "tokens",
        "cost_usd": "USD",
        "latency_ms": "ms",
    }
    lower = {"error_rate", "timeout_rate", "cost_usd", "latency_ms"}
    metrics = [
        {
            "name": name,
            "value": value,
            "unit": units[name],
            "direction": "lower_is_better" if name in lower else "higher_is_better",
            "scope": "benchmark",
            "aggregation": (
                "mean"
                if name not in {"input_tokens", "output_tokens", "cost_usd"}
                else "sum"
            ),
            "sample_count": count,
        }
        for name, value in values.items()
    ]
    return metrics


def _duration_ms(value: Any) -> float | None:
    if not isinstance(value, Mapping):
        return None
    from datetime import datetime

    try:
        started = datetime.fromisoformat(str(value["started_at"]).replace("Z", "+00:00"))
        finished = datetime.fromisoformat(str(value["finished_at"]).replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError):
        return None
    return max(0.0, (finished - started).total_seconds() * 1000)


def _integer(value: Any) -> int:
    return int(value) if _is_integer(value) else 0


def _is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _number(value: Any) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0


def _load_object(path: Path) -> Mapping[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return _mapping(data, str(path))


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value
