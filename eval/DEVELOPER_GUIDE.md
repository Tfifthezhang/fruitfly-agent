# Evaluation Guide

[Up: Eval](README.md)

Run one selected configuration, inspect reports, or add a benchmark adapter. Real execution uses networks, containers, and model services and may incur charges.

For the ordered Linux server procedure and executable YAML/JSON generators,
start with the [Server Evaluation Guide](SERVER_GUIDE.md).

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

Catalog preflight locates Harbor/Docker and checks Engine/Compose within five
seconds. Executable discovery does not prove Harbor imports or diagnose glibc.
Detailed [Harbor preparation](harbor/README.md) freezes tasks, records controller
packages, probes the mounted Linux runtime and records image identities.
Host and Docker network/proxy settings are separate paths. Pre-downloaded images
must match the complete references in the resolved task definitions. Prepare one
dedicated Linux Python/Agent environment, declare its read-only mounts in
`.fruitfly/eval-host.yaml`, and reuse it across compatible datasets.
Agent defaults and key files stay separate.

Use `FRUITFLY_EVAL_PACKAGE` to select complete source or wheel material when needed; see [installation material](README.md#select-installation-material).

## Create a CLI request

This example creates a request offline using the independent default configuration.
Prepare `.fruitfly/default-config.yaml` and its model catalog, and set
`FRUITFLY_BENCHMARK` to a registered catalog ID before running it:

```bash
.venv/bin/python - <<'PYTHON'
import json
import os
from pathlib import Path
from eval.catalog import builtin_catalog
from eval.contracts import EvaluationRequest

cwd = Path.cwd()
benchmark = os.environ['FRUITFLY_BENCHMARK']
builtin_catalog().get(benchmark)
request = EvaluationRequest.from_dict({
    'schema_version': 2,
    'runtime': {'working_directory': str(cwd)},
    'benchmark': {'id': benchmark, 'variant': 'smoke'},
    'execution': {'attempts': 1, 'concurrency': 1, 'timeout_seconds': 3600},
})
path = cwd / '.fruitfly/eval-request.json'
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(request.to_dict(), indent=2) + chr(10))
print(path)
PYTHON
```

After configuring the [machine file](harbor/README.md#configure-a-machine), prepare
the selection and check it. Preparation can download dependencies and build/start
containers; it makes no model requests. `check` only validates prepared local identities:

```bash
.venv/bin/python -m eval prepare --request .fruitfly/eval-request.json --tasks-only
.venv/bin/python -m eval prepare --request .fruitfly/eval-request.json
.venv/bin/python -m eval check --request .fruitfly/eval-request.json
```

The next command executes the model/container path and can incur charges:

```bash
.venv/bin/python -m eval run --request .fruitfly/eval-request.json --events jsonl
.venv/bin/python -m eval report '<EVALUATION_ID>' --json
```

| Option / result | Meaning |
|---|---|
| Runtime | Optional configuration path/profile; defaults to `.fruitfly/default-config.yaml` and its default profile. Working directory defaults to the process workspace. |
| Execution | Positive integer attempts, concurrency, and total job timeout |
| `benchmark.task_names` | Optional distinct exact names from the prepared selection; omission executes the full variant |
| `--output-root` | Override output location; use the same root to read reports |
| `--host-config` | Machine YAML override for prepare/check/run; defaults to workspace `.fruitfly/eval-host.yaml` |
| Exit codes | completed 0, failed 1, input/file error 2, blocked 3 |
| Request validation | Requires schema 2; unknown fields and experiment inputs are rejected |

`check` exits 0 for matching preparation, 3 when unavailable and 2 for input errors.
Verifier completeness/model connectivity remain explicitly unverified without
a real smoke trial. `prepare` creates no evaluation score or report.
Preparation schema 3 covers controller packages, selected/excluded tasks, Agent
and independent verifier environments. A missing or incompatible preparation
requires `prepare` again. Machine files remain schema 1. See
[environment preparation](harbor/README.md#prepare-check-and-run).

For an experimental configuration, explicitly supply `runtime.config_path` and
optionally `runtime.profile`. Relative paths resolve from `working_directory`.
Explicit empty strings and unknown fields fail; defaults never fall back to daily
configuration. Requests use schema 2 and one of `smoke`, `no_gpu` or `full`.

The runner parses the selected profile through the shared runtime specification,
preserves declared execution limits and tool scheduling, stages referenced main/auxiliary
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
| `artifacts/harbor/preparation.json`, `readiness.json` | Exact prepared task list, runtime/image identities and readiness evidence |
| `artifacts/harbor/control.json`, `cleanup.json` | Scoped stop token and cleanup state |

Trial setup probes the mounted Python and stages selected configuration. It never
installs the Agent, Python or pip packages. Agent runtime compatibility is checked
during preparation. Verifier dependencies use the separately prepared assets and
caches. The request sets the whole-job deadline; individual task/verifier limits
remain task-defined. No automatic timeout extension or failed-trial replay occurs.

Agent events are read around every 0.2 seconds and archived on completion. Job progress is emitted every five seconds. Setup, runner, verifier, exceptions, stderr, and non-JSON stdout are forwarded without log-body truncation. No observed Agent event can mean setup is still running.

`completed` means the report was assembled, `blocked` means preflight failed, and `failed` means runner/result validation failed. Missing usage/cost is unknown. Smoke validates one execution path.

Inspect report readiness and trial execution evidence separately from score.
Missing rewards are errors; a real zero remains a scored failure. Additional
qualified traceback exceptions and original log paths are retained even if Harbor
stores only its first exception. Timestamp states describe observations, not
proof that a phase succeeded.

```bash
.venv/bin/python -m eval stop '<EVALUATION_ID>' --output-root .fruitfly/eval
```

`stop` returns success only after cleanup is confirmed, or for an already finished
job. A pending request or cleanup failure returns nonzero. Ctrl+C/SIGTERM and job
timeout use the same process/container retirement. Normal Agent completion keeps
task background services alive for the verifier. See
[ownership limits](harbor/README.md#stop-and-inspect-ownership).

## Diagnose failures

| Symptom | Check |
|---|---|
| Registry connection error | Host proxy/VPN and underlying exception in harbor.log |
| Image failure | Engine network, registry auth, tag/architecture, and disk space |
| Setup timeout | Preparation/readiness identities, setup.log and runtime probe; no per-task Agent downloads are expected |
| No Agent events | Setup and trial logs |
| Missing reward | Verifier logs and adapter reward mapping |

The run consumes explicit frozen local tasks rather than resolving a registry
again. A legacy registry connection failure retries at most three times, within
the same timeout, only before a Harbor job exists. Existing jobs and
model/setup/verifier failures are not automatically replayed. Keep TLS
verification; preserve logs and keep secrets out of reports. Never overwrite
Harbor's private content-addressed cache to repair a verifier setup script.

## Add a benchmark

| Step | Action |
|---|---|
| 1 | Declare dataset/version and one exact smoke task. The shared selections are `smoke`, `no_gpu` and `full`. |
| 2 | Subclass `HarborBenchmarkAdapter` and call `harbor_descriptor`. Preparation, runtime mounts, shared/separate verifiers, credentials, commands, lifecycle, logs, trajectories and parsing are shared by [the Harbor package](harbor/README.md). Other backends implement `BenchmarkAdapter`. |
| 3 | Export/register its unique ID in [catalog.py](catalog.py). |
| 4 | Declare machine/cache requirements through the host file, and explicit verifier dependency recipes or exact setup patches where needed. Test preparation, frozen task coverage, failures, rewards and reports offline. |
| 5 | Inspect catalog output; authorize real smoke separately. |

`BenchmarkAdapter.run(request_path=..., result_path=..., variant=..., progress=...)`
consumes the single-configuration request and writes schema-2 results containing
status, metrics, errors, artifacts, and trials. A custom Harbor task needs
instructions, task.toml, an environment and an official verifier definition.
Dataset identity and its smoke task belong to the adapter declaration. Resource
filtering and image/runtime diagnostics belong to the shared Harbor layer. Other
runners implement the same request/result interface; runtime ownership stays outside Eval.
