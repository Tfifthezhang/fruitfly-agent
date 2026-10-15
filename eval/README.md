# Eval

[Up: FruitFlyAgent](../README.md)

Run a benchmark with one selected harness configuration and generate task results and reports. Harbor owns task containers and official verifiers. Eval remains an optional external consumer of the normal Agent.

## Install and inspect

Harbor requires Python 3.12+, Docker Engine, and Compose v2. Real evaluations download tasks/images and call models, potentially incurring charges.

```bash
.venv/bin/python -m pip install -e '.[benchmarks]'
docker info
docker compose version
.venv/bin/python -m eval catalog --json
```

| Item | Support |
|---|---|
| Benchmarks | Terminal-Bench 2.0, SWE-bench Verified |
| Backend | Local Docker through Harbor |
| Variants | Fixed single-task `smoke`, Terminal-Bench five-task `starter`, full `no_gpu`, full `gpu` |
| Formats | Request, runner result, trial, and report schema 2 |
| Output | `.fruitfly/eval/<evaluation-id>/` |

Preflight checks executable/Engine/Compose availability. It does not prove image availability, free disk space, architecture compatibility, or model connectivity.

## Run and read reports

Use the Eval CLI to run a selected saved configuration and create independent task sessions. Use `/improvement → Start improvement → Benchmark tasks` for iterative improvement against a bounded original task set. See the [developer guide](DEVELOPER_GUIDE.md) for request examples, logs, and adapter development.

| Command | Purpose |
|---|---|
| `python -m eval catalog --json` | Inspect benchmarks, variants, and availability |
| `python -m eval run --request request.json` | Execute one explicitly authorized benchmark request |
| `python -m eval report EVALUATION_ID --json` | Read a stored report |

Reports include the selected configuration, execution settings, scores, available usage/cost/latency, errors, and artifact paths. Task records include actual runtime manifests when Harbor supplies them. Missing measurements remain unknown. `completed` means report generation finished; inspect task outcomes. A smoke run does not establish general capability.

For a small standalone evaluation, set the Terminal-Bench request variant to `starter`. The improvement menu also offers **Terminal-Bench → Starter batch · 5 CPU tasks**. See [public task formats and selected tasks](benchmarks/TASKS.md). The interactive starter uses one attempt and concurrency one, with a four-hour whole-job deadline.

Requests reject unsupported experiment fields. Stored JSON and Markdown reports are read directly without regeneration. Run and Lab own controlled improvement experiments; Eval supplies an optional official-task executor and evidence export.

## Select installation material

Harbor installs the validated source checkout when available. Wheel installations must set `FRUITFLY_EVAL_PACKAGE` to an absolute path to complete FruitFlyAgent source or a built wheel. An explicit value overrides checkout discovery. Material must identify `fruitfly-agent` version `0.1`; invalid material fails before task startup.

Source installation stages package files, build inputs, README, and license notices. It excludes secrets, caches, and sessions. The selected profile and model catalog are copied into runner artifacts; secret values stay in the process environment. Workspace `.fruitfly/secrets.env` is used, with root `.env` fallback only when absent; process values take precedence. See [Configuration](../CONFIGURATION.md#files-and-precedence).

## Modules

| File / module | Responsibility |
|---|---|
| [Benchmarks](benchmarks/README.md) | Preflight, runner commands, official results, and logs |
| [contracts.py](contracts.py) | Single-configuration requests and task results |
| [execution.py](execution.py), [storage.py](storage.py) | Execution, reports, and artifacts |
| [report.py](report.py) | JSON and Markdown reports |
| [harbor_agent.py](harbor_agent.py) | Install/run the normal Agent inside task containers |
| [installation.py](installation.py) | Validate source or wheel build inputs |

Removing Eval leaves normal interaction and Lab development intact.

```bash
.venv/bin/python -m unittest discover -s tests/eval -t . -v
```

## Export tasks for improvement

[evidence.py](evidence.py) exports complete original task snapshots, canonical trajectories, official results and verifier logs under `artifacts/harbor/evidence/`. Missing task material is recorded as an export error without changing ordinary evaluation scores. Original schema-2 requests and reports remain unchanged. Evidence uses a separate schema-1 format.

[trial.py](trial.py) executes one frozen original task through Harbor with an injected versioned runtime packet. The bridge installs the frozen source and invokes the generic Run Application trial host; Harbor owns the original environment and verifier. This path requires source material, Harbor, Docker and authorized model/network calls. It rejects changed task material, unsupported datasets and incomplete receipts. `python -m eval trial --request REQUEST --output-root NEW_DIRECTORY --events jsonl` consumes a Run-generated request; it is not a schema-2 evaluation request.

`/improvement` can directly prepare a benchmark task set and start one explicitly confirmed improvement job, without preliminary Agent evaluation. See [Original task experiments](../fruitfly_agent/lab/optimization/experiments/README.md) for the task split, fixed versions, shared budgets, human adoption and limits.

[task_sets.py](task_sets.py) supplies `prepare_task_set` and the improvement-specific bounded CPU catalog. `python -m eval prepare --benchmark terminal-bench --variant starter --task-limit 5 --output-root NEW_DIRECTORY --events jsonl` downloads and freezes official tasks without constructing an Agent or inventing feedback. This operation requires Harbor, registry/network access, and a ready task environment; runtime improvement still owns model budgets and adoption.
