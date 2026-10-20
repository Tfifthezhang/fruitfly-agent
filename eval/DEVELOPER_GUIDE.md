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

## Use benchmark tasks in improvement

Open `/improvement` while idle. Select **Start improvement → Benchmark tasks**, choose a bounded CPU task set, inspect budget/acceptance/version details, then confirm **Start improvement**. Cancel is selected by default. The same Application job prepares task material and performs baseline, learning, candidate comparisons and confirmation; no preliminary evaluation is required. Original tasks and verifiers remain owned by Eval. A confirmed candidate still requires explicit human adoption.

For standalone benchmark scores and reports, use the CLI request below. Terminal-Bench's `starter` runs its fixed five-task batch; `smoke` runs one task. See [task formats](benchmarks/TASKS.md).

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

The runner copies the selected profile and catalog before starting Harbor. Per-task records include available actual runtime manifests. Source code, live Python heaps, and external services are not snapshotted. Ordinary evaluation does not freeze runtime source or learning state. The separately authorized [original-task improvement host](../fruitfly_agent/lab/improvement/README.md) does so before controlled trials.

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

Setup prefers an existing Python 3.11+ with venv, otherwise uses system/uv fallback. Setup commands are limited to 300 seconds; Harbor's default overall setup is 360 seconds. Interactive job limits are one hour for smoke, four hours for starter, and seven days for full datasets; individual task/verifier limits remain task-defined.

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

## Consume official execution evidence

The [evidence exporter](evidence.py) resolves the trial task through Harbor `TaskConfig.get_local_path()`, preserves complete task files and verifies the copied material hash. See the [upstream task configuration](https://github.com/laude-institute/harbor/blob/main/src/harbor/models/trial/config.py). This project pins Harbor 0.23.0. Export errors stay explicit. Boolean/missing rewards and runner exceptions do not become scored learning failures. Whole task snapshots include hidden verifier material for official reruns, but Lab's training projection does not send those files to the model.

The single-task [trial executor](trial.py) validates task/source identity before starting Harbor. It consumes a separately versioned Run-generated request, installs the frozen source and profile, and retrieves the actual Application invocation receipt. New runners can implement the injected original-task executor without changing Lab algorithms or ordinary evaluation requests. Default tests must use fake executors and Providers.

## Prepare a task set without Agent calls

[task_sets.py](task_sets.py) resolves the selected dataset with Harbor 0.23.0 `DatasetConfig.get_task_configs()` and downloads selected original bytes using `TaskClient.download_tasks()`. These APIs are used by [upstream task construction](https://github.com/laude-institute/harbor/blob/v0.23.0/src/harbor/trial/trial.py). Select exact fixed names or the first bounded CPU sample sorted by registry name. Freeze source revision, full material, instruction and verifier identities before any baseline runs. Unsupported multi-step/GPU tasks and changed copies fail explicitly. Preparation emits a task set, not an evaluation report or fabricated scores.
