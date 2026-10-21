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

Preflight locates Harbor/Docker, checks Engine/Compose within five seconds, and locates `nvidia-smi` for the GPU variant. It does not check images, free disk, all registries, or paid model connectivity. Inspect task images and architecture separately. Host and Docker network/proxy settings are separate paths. Terminal-Bench 2.1 uses the Hub dataset `terminal-bench/terminal-bench-2-1`; configure Harbor login/access if required. Pre-downloaded images must match the resolved task definitions.

Use `FRUITFLY_EVAL_PACKAGE` to select complete source or wheel material when needed; see [installation material](README.md#select-installation-material).

## Create a CLI request

This example creates a request offline using the independent default configuration.
Prepare `.fruitfly/default-config.yaml` and its model catalog before running it:

```bash
.venv/bin/python - <<'PY'
import json
from pathlib import Path
from eval.contracts import EvaluationRequest

cwd = Path.cwd()
request = EvaluationRequest.from_dict({
    'schema_version': 2,
    'runtime': {'working_directory': str(cwd)},
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
| Runtime | Optional configuration path/profile; defaults to `.fruitfly/default-config.yaml` and its default profile. Working directory defaults to the process workspace. |
| Execution | Positive integer attempts, concurrency, and total job timeout |
| `--output-root` | Override output location; use the same root to read reports |
| Exit codes | completed 0, failed 1, input/file error 2, blocked 3 |
| Request validation | Requires schema 2; unknown fields and experiment inputs are rejected |

For an experimental configuration, explicitly supply `runtime.config_path` and
optionally `runtime.profile`. Relative paths resolve from `working_directory`.
Explicit empty strings and unknown fields fail; defaults never fall back to daily
configuration. Existing fully specified schema-2 requests remain supported.

The runner normalizes the selected profile, stages referenced main/auxiliary
models, validates required credentials and rejects remote execution environments
before starting Harbor. `runtime.json` records source, selected profile and
configuration/model hashes and unrestricted execution mode. Each attempt consumes the same staged files;
subsequent edits to source configuration do not change the job. Eval explicitly
passes `--unrestricted` inside each task container. Its host strategy omits
application permission wrapping and approval while retaining the task environment.
Harbor/Docker supply isolation; runtime deadlines, cancellation and cleanup remain.
No permission configuration file is staged.

Per-task records include available actual runtime manifests. Live Python heaps
and external services are not snapshotted. Installation input hashes identify the
source/wheel actually staged for each task. Eval does not freeze or optimize
learning state.

## Follow execution and reports

| Path under `.fruitfly/eval/<id>/` | Contents |
|---|---|
| `request.json` | Selected configuration and execution options |
| `report.md`, `report.json` | Scores, errors, available measurements, and artifact paths |
| `trials/` | Parsed task results and actual runtime metadata when supplied |
| `artifacts/runner-result.json` | Adapter result |
| Harbor trial `agent/installation.json`, `trajectory.json` | Installation hashes and ATIF projection |
| `artifacts/harbor/config.yaml`, `models.yaml` | Normalized selected runtime files; credentials remain environment references |
| `artifacts/harbor/runtime.json` | Source/content identity and unrestricted execution mode |
| `artifacts/harbor/harbor.log` | Final runner attempt |
| `artifacts/harbor/harbor-attempt-*.log` | Earlier registry connection attempts |
| Harbor job/trial directories | Setup/session/events, verifier logs, exceptions, and official results |

Setup prefers an existing Python 3.11+ with venv, otherwise uses system/uv fallback. Setup commands are limited to 300 seconds; Harbor's default overall setup is 360 seconds. The request sets the whole-job deadline; individual task/verifier limits remain task-defined.

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
| 1 | Declare dataset/version, an exact smoke task and optional exact subsets. |
| 2 | For Harbor tasks, subclass `HarborBenchmarkAdapter` and call `harbor_descriptor`; default resolution, runtime snapshots, credentials, permissions, installation, commands, logs, trajectories and parsing are shared. Other backends implement `BenchmarkAdapter`. |
| 3 | Export/register its unique ID in [catalog.py](catalog.py). |
| 4 | Test request validation, commands, preflight, failures, rewards, and reports offline. |
| 5 | Inspect catalog output; authorize real smoke separately. |

`BenchmarkAdapter.run(request_path=..., result_path=..., variant=..., progress=...)` consumes the single-configuration request and writes schema-2 results containing status, metrics, errors, artifacts, and trials. A custom Harbor task needs instructions, task.toml, an environment, and an independent verifier. Dataset identity and exact task subsets belong to the adapter declaration. Other runners implement the same request/result interface; runtime ownership stays outside Eval.

