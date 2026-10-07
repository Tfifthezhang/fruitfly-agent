# Evaluation Guide

[Up: Eval](README.md)

Run and diagnose external benchmarks, or add an adapter. Execute commands from the project root. Real evaluation uses networks, containers, and model services and may incur charges.

## Prepare the environment

| Requirement | Current contract |
|---|---|
| Host | macOS/Linux; native Windows unsupported, WSL2 unverified |
| Python | 3.12+ for Harbor; Agent itself requires 3.11+ |
| Harbor | `0.23.0`, pinned by the benchmarks extra |
| Docker | Reachable Engine and Compose v2 |
| Model | Configured catalog/profile and secret environment |
| Task images | Read each task's `environment.docker_image`, Dockerfile, and Compose configuration. |

```bash
.venv/bin/python -m pip install -e '.[benchmarks]'
docker info
docker compose version
.venv/bin/python -m eval catalog --json
```

Pre-pull or build task images to separate image preparation failures from Agent failures. A dataset can require multiple images. Use actual task tags/digests and inspect architecture; downloaded amd64 images still require compatible execution on Apple Silicon. Check `docker system df` and Docker Desktop's virtual disk allocation.

| Preflight check | What it proves |
|---|---|
| Harbor executable | Command can be located. |
| Docker CLI | Client exists. |
| `docker info` | Daemon reachable within a 5-second check. |
| Compose v2 | Compose command works within a 5-second check. |
| `nvidia-smi` for GPU variant | NVIDIA tool exists; not a container GPU test. |

Preflight does not check cached images, free disk, every registry, or paid model connectivity. Host, Docker Engine, and container proxy settings are separate network paths.

Select complete source or wheel material with `FRUITFLY_EVAL_PACKAGE` when the host is installed from a wheel. Source/editable use can discover the complete checkout. See [installation material](README.md#select-installation-material) for validation, staging, and environment precedence. Retain the exact artifact hash and corresponding source; version `0.1` alone does not establish reproducibility.

## Run through the terminal

| Step | Action |
|---|---|
| 1 | Start a normal Agent session with the desired runtime. |
| 2 | Enter `/eval` while idle. |
| 3 | Choose current setup or mechanism comparison, benchmark, and resource variant. |
| 4 | For comparison, select an enabled non-capability mechanism that can be disabled independently. |
| 5 | Review costs and explicitly choose **Run**. |

Esc or `back` returns one level; `q` returns to chat. The frontend waits until evaluation returns and does not expose normal chat or the optimization cancellation panel during it. Each evaluation runs separately from the current conversation.

## Create a CLI request

Use a saved evaluation's `request.json`, or build one from a normal Session's manifest. This example assumes the default configuration/profile; replace the Session path:

```bash
.venv/bin/python - '.fruitfly/sessions/<SESSION_FILE>.jsonl' <<'PY'
import json
import sys
from pathlib import Path
from eval.contracts import EvaluationRequest

cwd = Path.cwd()
entries = [json.loads(line) for line in Path(sys.argv[1]).read_text().splitlines() if line.strip()]
manifest = next(entry['manifest'] for entry in reversed(entries)
                if entry.get('type') == 'meta' and entry.get('kind') == 'runtimeManifest')
request = EvaluationRequest.from_dict({
    'schema_version': 1,
    'mode': 'current_setup',
    'runtime': {'manifest': manifest, 'config_path': str(cwd / '.fruitfly/config.yaml'),
                'profile': 'default', 'working_directory': str(cwd)},
    'benchmark': {'id': 'terminal-bench', 'variant': 'smoke'},
    'comparison': None,
    'execution': {'attempts': 1, 'concurrency': 1, 'seed': 0, 'timeout_seconds': 3600},
})
path = cwd / '.fruitfly/eval-request.json'
path.write_text(json.dumps(request.to_dict(), indent=2) + '\n')
print(path)
PY
```

Check the plan without calling a model:

```bash
.venv/bin/python -m eval plan --request .fruitfly/eval-request.json --output .fruitfly/eval-plan.json
```

The next command runs the paid/network/container path:

```bash
.venv/bin/python -m eval run --request .fruitfly/eval-request.json --events jsonl
.venv/bin/python -m eval report '<EVALUATION_ID>' --json
```

| CLI behavior | Meaning |
|---|---|
| `plan` / `run` IDs | Each command creates its own ID. |
| Saved plan execution | No CLI for executing a specified plan or resuming an interrupted job. |
| `--output-root` | Use the same root when reading reports. |
| Exit codes | completed 0, failed 1, input/file error 2, blocked 3 |

Copied requests do not snapshot current source/configuration. Confirm manifest consistency before running.

## Follow execution

| Stage | Owner | Evidence |
|---|---|---|
| Request and plan | Eval | `request.json`, `plan.json` |
| Dataset and image preparation | Harbor/Docker | `harbor.log`, job/trial logs |
| Agent setup | Container | `agent/setup.log` |
| Agent run | Normal FruitFlyAgent one-shot CLI | `agent/session.jsonl`, `agent/events.jsonl` |
| Verification | Official task verifier | Verifier logs and trial result |
| Reporting | Eval | Trial artifacts, `report.md`, `report.json` |

Setup prefers an existing Python 3.11+ with venv, otherwise uses system/uv fallback. Container setup output is tee'd to `/logs/agent/setup.log`. A setup command is limited to 300 seconds; Harbor's default overall Agent setup is 360 seconds. Interactive job limits are 1 hour for smoke and 7 days for full runs; task execution/verifier limits remain task-defined.

| Live observation | Behavior |
|---|---|
| Agent events | Incrementally read around every 0.2 seconds; archive full events on completion. |
| Job state | Every 5 seconds: elapsed time, finished tasks, observed Agent activity. |
| Waiting state | No observed Agent event yet; does not prove a hang. |
| Diagnostics | Setup, runner, verifier, exception, stderr, and non-JSON stdout forwarded without log-body truncation. |

## Read artifacts

| Path under `.fruitfly/eval/<id>/` | Contents |
|---|---|
| `request.json`, `plan.json` | Declared and frozen conditions |
| `report.md`, `report.json` | Aggregate results |
| `trials/` | Parsed trial records |
| `artifacts/harbor/<condition-id>/harbor.log` | Final runner attempt |
| `harbor-attempt-1.log`, `harbor-attempt-2.log` | Earlier registry connection attempts, when applicable |
| Harbor job/trial directories | Job results, Agent setup/session/events, verifier logs, and exceptions |

Files can be absent when execution never reached their stage. The current chat Session does not contain evaluation logs.

| Status / value | Interpretation |
|---|---|
| `completed` | Report assembled; inspect rewards and error/timeout rates. |
| `blocked` | Required preflight failed. |
| `failed` | Runner or result validation failed; not a zero capability score. |
| Trial `passed` | Public parser found a valid reward at least 1. |
| Missing usage/cost | Unknown, not zero. |

Review parsing for graded or multiple rewards. Smoke verifies one execution path, not general capability.

## Diagnose failures

| Symptom | Check |
|---|---|
| Dataset registry connection error | Proxy/VPN in the same host process environment; first underlying exception in `harbor.log` |
| Image pull/build failure | Docker Engine network, authentication, image tag/architecture, and disk space |
| Setup timeout | Last download/install in `setup.log`; availability of Python/venv in the image |
| No Agent events | Setup and trial logs before inferring a hang |
| Manifest mismatch | Config, model, prompt contents, and enabled mechanism identity |
| Missing verifier reward | Verifier logs, reward files, and adapter mapping |

Registry ConnectError/ConnectTimeout/ReadTimeout may retry at most 3 times only before a Harbor job exists, within the same job timeout. Existing jobs, setup/model/verifier failures, and other errors are not automatically rerun. Keep TLS verification and preserve all attempt logs. Do not paste secrets or full environment dumps into reports.

## Add a benchmark

| Step | Action |
|---|---|
| 1 | Fix dataset identity/version, exact smoke task, resources, network surfaces, reward fields, and pass criteria. |
| 2 | Implement a [Benchmark adapter](benchmarks/README.md), reusing `HarborBenchmarkAdapter` where appropriate. |
| 3 | Export it and register its unique ID in [catalog.py](catalog.py). |
| 4 | Test catalog, plan, command, preflight, errors, reward parsing, and retained existing entries offline. |
| 5 | Inspect catalog/menu output; separately authorize a real smoke run. |

Menus consume catalog data; do not add benchmark-specific branches to Interactive or Run. A custom Docker image needs a complete Harbor task: instruction, `task.toml`, environment, and an independent verifier. A bare image is not a benchmark.

| Custom source | Integration |
|---|---|
| Published Harbor dataset | Register an adapter with fixed source metadata. |
| Local task directory | Override the Eval command's dataset argument with Harbor `--path`; fix source identity and preserve Agent/runtime/resource options. |
| Non-Harbor runner | Extend Eval plan/execution/result contracts; the current plan runner descriptor is Harbor-specific. |

The current `/eval` form has no arbitrary image/path or benchmark-specific input fields.

## Reproducibility limits

| Concern | Limit |
|---|---|
| Task digest | Declared benchmark/version/variant/adapter/smoke identity, not every task file or image hash |
| Source/configuration | No automatic immutable snapshot; do not modify while running. |
| SWE-bench dataset | Save Harbor's actual resolved version/commit for formal studies. |
| Seed | Recorded in request/plan; not uniformly forwarded to Provider, task, and verifier. |
| Attempts/concurrency | Forwarded to Harbor. |

For formal research, record exact model/task/adapter identities, actual resources, repeats, budgets, failures, and raw evidence. See [Studies](studies/README.md), [Tests](../tests/eval/README.md), and the [Harbor repository](https://github.com/harbor-framework/harbor). The installed pinned version is the implementation reference.
