# Eval

[Up: FruitFlyAgent](../README.md)

Optional benchmark evaluation using the Agent's existing public capabilities. Harbor owns task containers and official verifiers; Eval freezes conditions and reports results.

## Available evaluations

| Item | Current support |
|---|---|
| Studies | `current_setup`, `mechanism_comparison` |
| Benchmarks | Terminal-Bench 2.0, SWE-bench Verified |
| Backend | Local Docker through Harbor |
| Formats | Request, frozen plan, trial, and report schema v1 |
| Artifacts | `.fruitfly/eval/<evaluation-id>/` |

## Install and inspect

Harbor requires Python 3.12+, Docker Engine, and Compose v2. Installation downloads dependencies; real evaluations download tasks/images and call models, potentially incurring charges.

```bash
.venv/bin/python -m pip install -e '.[benchmarks]'
docker info
docker compose version
.venv/bin/python -m eval catalog --json
```

Use `/eval` in an idle Agent session, or run the standalone CLI with an `EvaluationRequest`. Catalog inspection does not run a benchmark or request a model. See the [developer guide](DEVELOPER_GUIDE.md) for complete setup, request creation, logs, and extension.

| Variant | Behavior |
|---|---|
| `smoke` | Fixed single task; connectivity and execution check |
| `no_gpu` | Full dataset without NVIDIA preflight |
| `gpu` | Full dataset with NVIDIA-tool preflight |

Resource labels do not override task CPU/RAM/time limits. Preflight does not prove image availability, architecture compatibility, free disk space, or Provider connectivity.

## Select installation material

Harbor installs the complete validated source checkout by default when running from source or an editable installation. Wheel installations must set `FRUITFLY_EVAL_PACKAGE` to an absolute path to a complete FruitFlyAgent source directory or a built wheel. An explicit value also overrides checkout discovery. Material must identify `fruitfly-agent` version `0.1`; missing build inputs or invalid wheels fail before container task startup.

Source installation stages Python package files, `pyproject.toml`, `README.md`, and license notices. It excludes local secrets, caches, and sessions. Wheel installation uploads the selected wheel. Neither path snapshots arbitrary learning state or proves source equivalence; retain the exact source/artifact and its hash for research. Dependency installation inside real containers still uses the network. The benchmark runner reads workspace `.fruitfly/secrets.env`, falling back to root `.env` only when absent; files are not merged and process environment values take precedence. See [Configuration](../CONFIGURATION.md#files-and-precedence).

## Commands and results

| Command | Purpose |
|---|---|
| `python -m eval catalog --json` | Inspect modes, benchmarks, variants, and availability. |
| `python -m eval plan --request request.json` | Validate and freeze declared conditions. |
| `python -m eval run --request request.json` | Run an explicitly authorized evaluation. |
| `python -m eval report EVALUATION_ID --json` | Read a saved report. |

`completed` means report generation finished, not that every task passed. Missing usage is unknown, not zero. Synthetic adapters and single-task smoke runs do not establish benchmark capability.

## Modules

| Module / file | Responsibility |
|---|---|
| [Benchmarks](benchmarks/README.md) | Dataset identities, preflight, runner commands, and official results |
| [Studies](studies/README.md) | Conditions and controlled mechanism ablations |
| [contracts.py](contracts.py), [planning.py](planning.py) | Requests and frozen conditions |
| [execution.py](execution.py), [storage.py](storage.py) | Execution, reports, and artifacts |
| [harbor_agent.py](harbor_agent.py) | Install and run the normal Agent in task containers |
| [installation.py](installation.py) | Validate source build inputs or wheel identity before installation |
| [Developer guide](DEVELOPER_GUIDE.md) | Running, diagnosis, and extension |

Eval does not define production lifecycle or algorithm interfaces. Removing it must leave normal interaction intact.

```bash
.venv/bin/python -m unittest discover -s tests/eval -t . -v
```
