# Eval

[Up: FruitFlyAgent](../README.md)

Evaluate the native FruitFlyAgent in benchmark task containers. Harbor owns the
environments, task deadlines and official verifiers. Eval mounts a prepared Agent
runtime, passes one saved configuration and collects outcomes, trajectories and reports.
Interactive improvement remains independent of Eval.

The independent [experiment CLI](../fruitfly_agent/experiments/README.md) provides
`fruitfly-agent-lab eval` with file defaults, alongside separate Improvement and
RSI commands. Existing `fruitfly-agent-eval` and `python -m eval` invocations remain
supported. [api.py](api.py) exposes reusable operations; [service.py](service.py)
owns preparation/check/report/stop without argument parsing or runtime imports.

`prepare --tasks-only` resolves and freezes task definitions, reports exclusions,
build contexts and exact local image references, and starts no containers. Full
preparation records controller versions and declared dependency conflicts. Changed
controller packages invalidate readiness; reviewed metadata conflicts remain
explicitly unverified rather than being hidden by a successful smoke.

For ordered server setup, private-file transfer, YAML/JSON generation and the
smoke-to-full workflow, use the [Server Evaluation Guide](SERVER_GUIDE.md).

## Install and inspect

Use Python 3.12+, Docker Engine and Compose v2:

```bash
.venv/bin/python -m pip install -e '.[benchmarks]'
docker info
docker compose version
.venv/bin/python -m eval catalog --json
```

| Item | Support |
|---|---|
| Datasets | Terminal-Bench 2.1, Terminal-Bench 4.0.0, SWE-bench Verified; see [task selections](benchmarks/TASKS.md) |
| Backend | Docker through Harbor `0.23.0` |
| Selection | `smoke`, tasks without GPU requirements (`no_gpu`), or all tasks (`full`) |
| Formats | Requests and host files have one format without version markers; results/reports and preparation receipts retain their record versions |
| Output | `.fruitfly/eval/<evaluation-id>/` |

Preflight checks Harbor/Docker availability and Engine/Compose access. It does
not prove dataset access, cached image tags, architecture compatibility, disk
space or model connectivity. All datasets share the same three selections.
`no_gpu` excludes declared GPU requirements across effective roles, steps and
Compose services before image preparation; `full` retains all resolved tasks.
Task resources remain official. Review exclusions and scope in the preparation receipt.

Shared and separate verifier environments use the same Harbor adapter. Independent
verifiers receive prepared dependency assets/caches, without Agent runtime mounts
or model credentials. Harbor owns artifact transfer and scoring.

## Run an evaluation

Unless `runtime.config_path` is supplied, Eval selects the workspace's
`.fruitfly/default-config.yaml` and its default profile. The runtime object and
profile may be omitted; `working_directory` defaults to the process workspace.
Relative configuration paths resolve from that workspace. Explicit configurations
remain supported. Missing/invalid defaults fail without daily fallback. Prepare
the independent [default files](../CONFIGURATION.md#restore-default-configuration)
before execution.

Create a request using the [evaluation guide](DEVELOPER_GUIDE.md), and configure
the [machine runtime and dependencies](harbor/README.md), then run:

```bash
# Preparation can download/build/start containers; no model requests.
.venv/bin/python -m eval prepare --request .fruitfly/eval-request.json --tasks-only
.venv/bin/python -m eval prepare --request .fruitfly/eval-request.json
.venv/bin/python -m eval check --request .fruitfly/eval-request.json
# Agent/model requests and official verification; may incur charges.
.venv/bin/python -m eval run --request .fruitfly/eval-request.json --events jsonl
.venv/bin/python -m eval report '<EVALUATION_ID>' --json
```

Use `stop '<EVALUATION_ID>'` to request scoped shutdown and confirm cleanup.
Each attempt starts a separate native Agent session. `completed` means reports
were assembled; inspect trial failures and infrastructure errors. A smoke result
is not a representative full-dataset score. See [task selection](benchmarks/TASKS.md).

## Select installation material

A complete source checkout is discovered automatically. Set `FRUITFLY_EVAL_PACKAGE`
to an absolute source directory or built wheel to override it during `prepare`. Material must
identify `fruitfly-agent` version `0.1`. Source staging includes package Python,
build inputs, README and license notices, excluding local secrets and sessions.
Preparation freezes that source and an existing Linux runtime. Each trial records
SHA-256 source/wheel inputs in `agent/installation.json`. The trial installation
hook probes the mounted interpreter and stages configuration; it never installs
Python, creates a venv or runs pip. Task Python versions remain independent.

The selected profile uses the [shared runtime specification](../fruitfly_agent/runtime_spec/README.md).
Declared execution parameters are validated and preserved during staging.
Schema-2 staging preserves the full H/S/I documents and role bindings through the
shared loader. Referenced model definitions are staged before Harbor starts;
inactive roles retain catalog metadata without requiring unused credentials. Enabled mechanism dependencies are resolved through
Catalog without Provider construction. Missing required credentials and remote
execution environments are rejected before launching tasks. Unselected models
and unrelated credential variables are excluded. Explicit
content-addressed prompt and component bindings are hash-checked and copied into
each task's artifact store. Mutable host memory, Skill directories, arbitrary
workspace files and external services are not copied. Use inline initial text,
explicit immutable bindings or inputs already provided by the task. State created
inside an attempt is discarded with its environment; Eval does not carry learning
between tasks or optimize the Agent.

Secrets come from the workspace `.fruitfly/secrets.env`
and process environment; process values win. Model keys and enabled mechanisms'
Catalog-declared credentials reach the Agent through environment variables.
Values are absent from request JSON and runner arguments. See
[Configuration](../CONFIGURATION.md#files-and-precedence).

The container invokes the normal CLI with explicit `--unrestricted`. The chosen
host strategy leaves the task backend unwrapped, allows tools without approval
and preserves the task environment. Application directory, credential-file and
Session-file restrictions do not apply. Harbor/Docker supply isolation; timeout,
cancellation, cleanup and logging remain active. No permission settings file is
staged or loaded. Agent configuration contains no permission preference. Task
images can still need network access for task and verifier dependencies. Those
downloads use separately prepared assets/caches, without making the Agent runtime writable.

## Inspect results

| Artifact | Meaning |
|---|---|
| `report.json`, `report.md`, `trials/` | Official outcomes and available measurements |
| `artifacts/harbor/config.yaml`, `models.yaml` | Selected configuration |
| `artifacts/harbor/runtime.json` | Source selection, configuration/model hashes and unrestricted execution mode; no key values |
| `artifacts/harbor/preparation.json`, `readiness.json` | Controller package identity/conflicts, selected/excluded tasks, frozen runtime/images and checks; verifier/model execution can remain unverified |
| `artifacts/harbor/control.json`, `cleanup.json` | Tokenized process ownership and confirmed/unconfirmed cleanup |
| Harbor trial `agent/session.jsonl` | Authoritative canonical Session |
| Harbor trial `agent/trajectory.json` | ATIF-v1.7 projection with tools and observations |
| Harbor trial `agent/installation.json` | Exact source/wheel input hashes |
| Harbor trial `agent/runtime.json` | Shared frozen configuration/model/policy receipt |
| Harbor job/trial logs | Setup, Agent execution, verifier output and exceptions |
| Harbor trial `fruitfly-environments/` | Exact Agent and separate-verifier environment ownership for cleanup |

ATIF does not reconstruct request-specific context projections or auxiliary model
calls. Missing usage/cost remains unknown. The native Session retains original
records. Invalid conversion is reported in Agent metadata rather than fabricating
a complete trajectory.

Trial `execution` records and report `readiness` counts distinguish execution
errors from scored failures. Reward 0 can have a completed execution path.
Missing/ambiguous reward is an execution error. Original exceptions and rewards
remain available; qualified traceback summaries supplement the original logs.
End timestamps alone do not prove phase success. Existing metric rules continue
to exclude errored trials from the mean reward; raw rewards on errored trials
remain in execution evidence. No failures or zero rewards are automatically replayed.
Incomplete task/attempt coverage fails the report, retains available trial records
and omits aggregate benchmark metrics.

## Modules and offline checks

| Module | Responsibility |
|---|---|
| [Benchmarks](benchmarks/README.md) | Dataset declarations and shared Harbor adapter |
| [Harbor preparation](harbor/README.md) | Machine paths, frozen tasks/runtime, verifier assets/caches and lifecycle |
| [catalog.py](catalog.py), [contracts.py](contracts.py) | Discovery and single-configuration requests |
| [execution.py](execution.py), [storage.py](storage.py), [report.py](report.py) | Evaluation lifecycle, artifacts and reports |
| [runtime.py](runtime.py) | Shared profile parsing, immutable artifacts and credential staging |
| [installation.py](installation.py), [harbor_agent.py](harbor_agent.py) | Validate material, check mounts and launch the native Agent |
| [runner.py](runner.py), [results.py](results.py) | Process/log handling and official result parsing |
| [trajectory.py](trajectory.py) | Canonical Session to ATIF projection |

```bash
.venv/bin/python -m unittest discover -s tests/eval -t . -v
```

Offline tests use fake Providers and local processes. Real container, registry and
model compatibility require a separately authorized smoke run.

## Register benchmark execution for Improvement

[The optional adapter](improvement/README.md) registers prepared task material,
a runner and official development measurements with the independent Improvement
framework. Improvement proposes and compares; RSI adopts and continues; Eval runs
one fixed configuration at a time. Daily/non-container tasks need neither Eval
nor Harbor. No implicit evolution or additional `eval improve` CLI is installed.
