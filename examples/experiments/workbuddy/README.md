# Run WorkBuddy Code smoke and selected-task studies

[Up: Experiment examples](../README.md) · [Adapter contracts](../../../fruitfly_eval/workbuddy/README.md)

Use a dedicated Linux evaluation workspace. The installed entry is
`workbuddy-code`; it declares Code v1.0 and the exact smoke task
`api_contract-hard-openapi_params`. Real smoke and research model stages require
explicit authorization and can incur charges. This recipe does not start an
automatic multi-stage loop.

## Prepare the independent controller

Obtain a reviewed WorkBuddy source checkout and the official Code dataset through
its [upstream setup](https://github.com/Tencent/workbuddy-bench). Preserve the complete
`wb-bench-code-v1.0/` root, including `dataset.toml`, `tasks/` and `shared/`.
Cached task images alone do not supply these files or establish verifier readiness.

WorkBuddy pins Harbor 0.18.0. Keep that controller environment separate from the
FruitFlyAgent environment with its Harbor 0.23.0 benchmark extra. The WorkBuddy
controller also needs FruitFlyAgent's base dependencies so it can load the native
bridge and host credential services. Example installation steps below download
packages, but make no model requests; replace all paths:

```bash
uv sync --project /absolute/path/to/workbuddy-bench
uv pip install --python /absolute/path/to/workbuddy-bench/.venv/bin/python /absolute/path/to/fruitfly-agent
```

Do not install FruitFlyAgent's `[benchmarks]` extra into this controller. If you
resync WorkBuddy later, reinstall the Agent base dependencies and prepare again.
The separately mounted Agent Python environment must be Linux-compatible and
complete; follow the [server runtime guide](../../../fruitfly_eval/SERVER_GUIDE.md).

## Initialize and bind owner files

In a new workspace, using the installed `fruitfly-agent-lab`:

```bash
fruitfly-agent-lab init --source task-set --benchmark workbuddy-code --variant smoke
```

Initialization makes no model, Docker or download request. It writes generic
`tasks/benchmark.yaml`, the request and research file, an Eval host template and
`workbuddy-runner.yaml`. Existing authored files are never overwritten.
Configure the main file's normal system profile, model catalog and secret file.
For Go, select an `opencode-go` connection and bind its alias in
`models.roles.executor`; use verified model metadata rather than copying an
unconfirmed model ID. See [Go configuration](../../../fruitfly_agent/providers/connections/methods/opencode_go/README.md).

Set the host process path variables referenced by `eval-host.yaml`:

```bash
export FRUITFLY_EVAL_PYTHON_ROOT=/absolute/path/to/linux-python
export FRUITFLY_EVAL_VENV=/absolute/path/to/linux-agent-venv
export WORKBUDDY_DATASET_ROOT=/absolute/path/to/wb-bench-code-v1.0
```

Replace the controller checkout/Python paths in `workbuddy-runner.yaml`. Compute
its declared source checksum offline using the FruitFlyAgent Python environment:

```python
from pathlib import Path
from fruitfly_eval.workbuddy.configuration import runner_identity
print(runner_identity(Path('/absolute/path/to/workbuddy-bench'))['source_sha256'])
```

Put the printed checksum in `source_sha256`. Recompute deliberately after reviewed
source changes and prepare again. Do not repair frozen cache files manually.

## Prepare and inspect the smoke selection

```bash
# Freezes/inspects local task materials; no containers or model calls.
fruitfly-agent-lab eval prepare --tasks-only
# May prepare dependencies and start environment probes; no model inference.
fruitfly-agent-lab eval prepare
# Checks recorded source, interpreter, packages and images; runs no tasks.
fruitfly-agent-lab eval check
```

Check the exact selected task, official verifier resources and full image
references. Unknown/missing task names fail. Preflight does not establish account
entitlement or verifier success. A rootless host must support the selected runtime
mounts and actual Agent UID/GID. Native Linux can use the private Unix relay,
with one communication directory per trial and group-scoped socket permission;
otherwise configure the existing verified TLS relay fields in `eval-host.yaml`.
The actual Agent checks its relay descriptor before inference. A failed
`host.docker.internal` path does not prove every transport is unavailable.

## Run a fixed smoke only when authorized

```bash
# Starts the official task/verifier and model requests; charges may apply.
fruitfly-agent-lab eval run
```

Inspect the returned report and logs. A completed controller is not a passed task;
verify official reward, execution errors and retirement state. Alternatively,
select `next.stage: execute` in the initialized research file to publish the fixed
baseline batch directly into the study. Use one route intentionally; do not run
both merely to obtain the same baseline twice.

The direct Eval CLI also supports explicit requests and host paths:

```bash
fruitfly-agent-eval report EVALUATION_ID --output-root /path/to/eval-output --json
fruitfly-agent-eval stop EVALUATION_ID --output-root /path/to/eval-output
```

Use the actual output root from the invocation. Stop succeeds only after the
backend confirms retirement. Review unresolved work before requesting retries.

## Validate selected tasks and compare candidates

For a non-smoke subset, use request `benchmark.variant: full` and exact
`task_names` in the request or task collection. Copy
[selected.example.yaml](tasks/selected.example.yaml) and replace both task names.
Task-only preparation exposes the inventory before any model work. Collection
names are also passed to preparation, restricting environment probes. An
explicitly prepared subset cannot be used as an unrestricted full run.

Set attempts/concurrency on the research execute stage; leaf Eval requests remain
one attempt and concurrency one. Run the baseline with `{config: default-config.yaml}`
and a new output alias, then the selected complete candidate with
`{candidate: candidate-a}` against the same task population. Switching models uses
a separately selected complete system configuration, not inline WorkBuddy model
flags. It is a changed experimental condition and remains visible in comparison.

```bash
fruitfly-agent-lab improvement show --config .fruitfly/experiment.yaml
fruitfly-agent-lab improvement check --config .fruitfly/experiment.yaml
# Runs only next.stage; execute/propose/organize can incur charges.
fruitfly-agent-lab improvement step --config .fruitfly/experiment.yaml
```

Native results enter default measured compare without conversion. Use two aliases
in before/after order. A full baseline versus candidate subset needs explicit
`task_scope` equal to one input batch; missing or unequal task-attempt scope is
never silently intersected. See the [small-batch recipe](../small-batch/README.md)
and [metric definitions](../../../fruitfly_agent/lab/improvement/assessment/methods/measured/README.md).

Organize/propose remain independently selected stages. A candidate decision already
contains validated edits and complete export; baseline/evidence decisions do not.
Comparison does not activate candidates or run another stage automatically.

## Diagnose by responsibility

| Symptom | Inspect |
|---|---|
| Unknown `workbuddy-code` | Installed FruitFlyAgent source/version and entry-point environment |
| Runner source/version mismatch | Owner checksum, isolated controller and its lockfile |
| Missing smoke/task or plugin | Complete dataset root and exact names; image cache is insufficient |
| Missing/non-root user | Official user initialization and retained probe/setup logs |
| Go session-header failure | Frozen connected model entry; adapter must retain `opencode-go` identity |
| Relay cannot be reached | Agent identity, Unix mount or TLS hostname/CA/route; no inference needed to diagnose descriptor delivery |
| Missing reward | Official verifier logs and execution status; never assign a fabricated zero |
| `insufficient` comparison | Per-pair unknowns/mismatches, planned coverage and confidence interval |

Current registered scope is Code. Other WorkBuddy subsets and independent LLM
judge requirements are not implied by Code support. Offline fake rewards test
contracts, not benchmark quality or real server compatibility.

Task selection uses the exact local directory ID, for example
`api_contract-hard-openapi_params`. Preparation retains the official
`task.name`, for example `workbuddy/api_contract-hard-openapi_params`, separately
for engine results and attribution. The short name must match the directory ID.
Do not remove the organization prefix from official task files. Run preparation
again after updating the adapter.
