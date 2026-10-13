# Evaluation Guide

[Up: Eval](README.md)

Run one selected configuration, inspect reports, or add a benchmark adapter. Real execution uses networks, containers, and model services and may incur charges.

## Prepare the environment

| Requirement | Contract |
|---|---|
| Host | macOS/Linux; native Windows unsupported, WSL2 unverified |
| Python | Harbor requires 3.12+; Agent requires 3.11+ |
| Harbor | `0.23.0`, pinned by the benchmarks extra |
| Docker | Reachable Engine and Compose v2 |
| Model | Saved model catalog/profile and secret environment |

```bash
.venv/bin/python -m pip install -e '.[benchmarks]'
docker info
docker compose version
.venv/bin/python -m eval catalog --json
```

Preflight locates Harbor/Docker, checks Engine/Compose within five seconds, and locates `nvidia-smi` for the GPU variant. It does not check images, free disk, all registries, or paid model connectivity. Inspect task images and architecture separately. Host and Docker network/proxy settings are separate paths.

Use `FRUITFLY_EVAL_PACKAGE` to select complete source or wheel material when needed; see [installation material](README.md#select-installation-material).

## Run through the terminal

| Step | Action |
|---|---|
| 1 | Save the desired harness configuration and start an Agent session. |
| 2 | Enter `/eval` while idle. |
| 3 | Choose a benchmark and resource variant. |
| 4 | Review cost requirements and explicitly choose **Run**. |

Esc/back returns one page; q returns to chat. Confirmation defaults to Back. Evaluation uses an independent process and task sessions. The terminal waits for completion and restores its display on cancellation/error.

## Create a CLI request

This example creates a request offline. Replace `default` with the selected saved profile if needed:

```bash
.venv/bin/python - <<'PY'
import json
from pathlib import Path
from eval.contracts import EvaluationRequest

cwd = Path.cwd()
request = EvaluationRequest.from_dict({
    'schema_version': 2,
    'runtime': {'config_path': str(cwd / '.fruitfly/config.yaml'),
                'profile': 'default', 'working_directory': str(cwd)},
    'benchmark': {'id': 'terminal-bench', 'variant': 'smoke'},
    'execution': {'attempts': 1, 'concurrency': 1, 'timeout_seconds': 3600},
})
path = cwd / '.fruitfly/eval-request.json'
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(request.to_dict(), indent=2) + '\n')
print(path)
PY
```

The next command executes the paid/network/container path:

```bash
.venv/bin/python -m eval run --request .fruitfly/eval-request.json --events jsonl
.venv/bin/python -m eval report '<EVALUATION_ID>' --json
```

| Option / result | Meaning |
|---|---|
| Runtime | Configuration path, profile, and working directory |
| Execution | Positive integer attempts, concurrency, and total job timeout |
| `--output-root` | Override output location; use the same root to read reports |
| Exit codes | completed 0, failed 1, input/file error 2, blocked 3 |
| Request validation | Requires schema 2; unknown fields and experiment inputs are rejected |

The runner copies the selected profile and catalog before starting Harbor. Per-task records include available actual runtime manifests. Source code, live Python heaps, and external services are not snapshotted. Researchers manage experiments and their own records externally.

## Follow execution and reports

| Path under `.fruitfly/eval/<id>/` | Contents |
|---|---|
| `request.json` | Selected configuration and execution options |
| `report.md`, `report.json` | Scores, errors, available measurements, and artifact paths |
| `trials/` | Parsed task results and actual runtime metadata when supplied |
| `artifacts/runner-result.json` | Adapter result |
| `artifacts/harbor/config.yaml`, `models.yaml` | Copied runtime files; secret values are excluded by configuration convention |
| `artifacts/harbor/harbor.log` | Final runner attempt |
| `artifacts/harbor/harbor-attempt-*.log` | Earlier registry connection attempts |
| Harbor job/trial directories | Setup/session/events, verifier logs, exceptions, and official results |

Setup prefers an existing Python 3.11+ with venv, otherwise uses system/uv fallback. Setup commands are limited to 300 seconds; Harbor's default overall setup is 360 seconds. Interactive job limits are one hour for smoke and seven days for full datasets; individual task/verifier limits remain task-defined.

Agent events are read around every 0.2 seconds and archived on completion. Job progress is emitted every five seconds. Setup, runner, verifier, exceptions, stderr, and non-JSON stdout are forwarded without log-body truncation. No observed Agent event can mean setup is still running.

`completed` means the report was assembled, `blocked` means preflight failed, and `failed` means runner/result validation failed. Missing usage/cost is unknown. Smoke validates one execution path.

## Diagnose failures

| Symptom | Check |
|---|---|
| Registry connection error | Host proxy/VPN and underlying exception in harbor.log |
| Image failure | Engine network, registry auth, tag/architecture, and disk space |
| Setup timeout | Last setup.log download/install and Python/venv availability |
| No Agent events | Setup and trial logs |
| Missing reward | Verifier logs and adapter reward mapping |

Registry connection failures retry at most three times, within the same timeout, only before a Harbor job exists. Existing jobs and model/setup/verifier failures are not automatically replayed. Keep TLS verification; preserve logs and keep secrets out of reports.

## Add a benchmark

| Step | Action |
|---|---|
| 1 | Declare dataset/version, smoke task, resources, network surfaces, and reward fields. |
| 2 | Implement a [Benchmark adapter](benchmarks/README.md); reuse HarborBenchmarkAdapter when appropriate. |
| 3 | Export/register its unique ID in [catalog.py](catalog.py). |
| 4 | Test request validation, commands, preflight, failures, rewards, and reports offline. |
| 5 | Inspect catalog/menu output; authorize real smoke separately. |

`BenchmarkAdapter.run(request_path=..., result_path=..., variant=..., progress=...)` consumes the single-configuration request and writes schema-2 results containing status, metrics, errors, artifacts, and trials. A custom Harbor task needs instructions, task.toml, an environment, and an independent verifier. The terminal does not accept arbitrary image/path fields. Other runners implement the same request/result interface; runtime ownership stays outside Eval.
