# Run TB4 Improvement on a Linux server

[Up: Experiment Files](README.md)

Start a fresh experiment on the declared `terminal-bench-4` smoke task,
`interleaved-vigenere`. No previous local `.fruitfly` files or experiment results
are required. Task-set search uses the same shared comparison path for one task
at concurrency 1 and for larger collections.

## Install the controller and Linux Agent runtime

Run on the Linux server, from a downloaded FruitFlyAgent source checkout. Python
3.12+, a working Docker daemon with Compose, and `uv` are prerequisites for this
recipe. The controller needs the pinned optional Harbor dependency; the Agent
needs a complete Linux Python installation visible inside task containers.
Installation downloads packages. A macOS venv cannot serve as that runtime.

For an existing server, first inspect and reuse validated environments using the
[server guide](../../fruitfly_eval/SERVER_GUIDE.md#1-inspect-the-server-before-installing).
For a **new installation only**, using previously unused environment paths:

```bash
umask 022
export FRUITFLY_EVAL_ROOT="$HOME/fruitfly-eval-runtime"
export UV_PYTHON_INSTALL_DIR="$FRUITFLY_EVAL_ROOT/python"
uv python install 3.12
export FRUITFLY_EVAL_BASE_PYTHON="$(uv python find --managed-python --system 3.12)"
export FRUITFLY_EVAL_PYTHON_ROOT="$("$FRUITFLY_EVAL_BASE_PYTHON" -c 'import sys; print(sys.base_prefix)')"
export FRUITFLY_EVAL_VENV="$FRUITFLY_EVAL_ROOT/agent-venv"

uv venv --python "$FRUITFLY_EVAL_BASE_PYTHON" .venv
uv pip install --python .venv/bin/python -e '.[benchmarks]'
uv pip check --python .venv/bin/python
uv venv --python "$FRUITFLY_EVAL_BASE_PYTHON" "$FRUITFLY_EVAL_VENV"
uv pip install --python "$FRUITFLY_EVAL_VENV/bin/python" --link-mode copy .
uv pip check --python "$FRUITFLY_EVAL_VENV/bin/python"

export FRUITFLY_LAB="$PWD/.venv/bin/fruitfly-agent-lab"
```

`FRUITFLY_LAB` is the controller entry point. The dedicated Agent venv is mounted
read-only into tasks with its complete base Python, preserving absolute links.
The controller also freezes the selected project source during preparation.
Do not mount the entire checkout or `/usr`. For glibc, native libraries,
certificates, dependency snapshots and proxies, follow
[environment preparation](../../fruitfly_eval/SERVER_GUIDE.md#3-establish-and-freeze-the-two-python-environments).

## Generate a fresh experiment

Keep the current shell's exported runtime paths. Choose a workspace whose
configuration destinations do not exist:

```bash
umask 077
export FRUITFLY_EXPERIMENT="$HOME/fruitfly-experiments/tb4-smoke"
mkdir -p "$FRUITFLY_EXPERIMENT"
"$FRUITFLY_LAB" --cwd "$FRUITFLY_EXPERIMENT" init --source task-set --benchmark terminal-bench-4
```

Initialization writes files only. Existing regular `models.yaml` and secret files
are preserved; other existing configuration destinations cause an error. It does
not overwrite defaults, reuse old candidate results or start Docker/model work.

| Generated file under `.fruitfly/` | Review before execution |
|---|---|
| `models.yaml` | Shared daily/experiment model ID, protocol, endpoint, capabilities, token limits and key variable name |
| `default-config.yaml` | Executor profile, enabled mechanisms and tool-call limit, initially 64 per turn |
| `components/H/`, `components/I/` | Execution/tool values, editor/evaluator prompts |
| `tasks/tb4-smoke.yaml`, `comparison.yaml` | Task material and fixed comparison rules |
| `experiment.yaml` | Baseline/task/comparison references, editable fields, fixed search/assessment settings and independent phase times |
| `secrets.env` | Fill the empty model key privately, or use the process environment; never commit it |
| `eval-request.json` | TB4 `smoke`, one attempt, concurrency 1 and whole-job timeout |
| `eval-host.yaml` | Linux runtime mounts, cache location and optional task/dependency settings |

The [request template](tb4-smoke-request.example.json) is identical to the generated
request. Its `working_directory: .` resolves from the experiment workspace when
used through `fruitfly-agent-lab --cwd`. Omitted runtime config/profile inherits
`experiment.yaml` and the baseline profile. Request/host paths resolve relative to their declaring task document.

All three model roles initially use the catalog entry `deepseek-flash-openai`.
Change `models.roles.executor/editor/assessor` in `default-config.yaml` to select
different case-sensitive aliases from `models.yaml`. The
template's remote model compatibility is not established by offline checks.

Set `DEEPSEEK_API_KEY` privately. Keep `FRUITFLY_EVAL_PYTHON_ROOT` and
`FRUITFLY_EVAL_VENV` exported in each controller shell, including tmux, or replace
their placeholders in `eval-host.yaml` with the validated absolute server paths.
Runtime directories must be readable/traversable by the task user. Keep caches
outside runtime mounts. No credentials belong in the host YAML.

## Prepare and check before model execution

Stop at the first failed command. These steps make no model requests:

```bash
"$FRUITFLY_LAB" --cwd "$FRUITFLY_EXPERIMENT" eval prepare --tasks-only
"$FRUITFLY_LAB" --cwd "$FRUITFLY_EXPERIMENT" eval prepare
"$FRUITFLY_LAB" --cwd "$FRUITFLY_EXPERIMENT" improvement check
```

Task-only preparation can download definitions and inspect local image references.
Full preparation can pull/build/start environments and probes Agent/Verifier
compatibility. `improvement check` validates prepared inputs, credential presence,
effective mechanisms, component permissions, backend support and phase times
without constructing Providers or starting containers. It does not establish
successful model access or task quality. Review the selected task and exact image
identities; see [preparation evidence](../../fruitfly_eval/SERVER_GUIDE.md#8-prepare-check-and-run-the-smoke).

The [smoke experiment template](benchmark-smoke.example.yaml) automatically discovers legal targets supported by the runtime and task material. Add `edit` only to narrow that set. Check resolved fields and owner descriptions before running. Configure independent editor, execution and evaluator seconds under `timeouts`; counts and tokens are observations without admission quotas.

## Run and inspect the search

The following `run` makes model requests and executes official verification;
charges may apply. Use a persistent terminal on disconnect-prone connections:

```bash
"$FRUITFLY_LAB" --cwd "$FRUITFLY_EXPERIMENT" improvement run --events jsonl
"$FRUITFLY_LAB" --cwd "$FRUITFLY_EXPERIMENT" improvement list
"$FRUITFLY_LAB" --cwd "$FRUITFLY_EXPERIMENT" improvement report '<RUN_ID>' --json
# If needed, request scoped cancellation and wait for confirmed cleanup:
"$FRUITFLY_LAB" --cwd "$FRUITFLY_EXPERIMENT" improvement stop '<RUN_ID>'
```

Use the actual run ID. Candidate settings stay in the experiment's isolated run
copy; they do not edit the source checkout or baseline defaults. Official task
scores select results. Optional completed-process feedback is disabled in this
minimal template; the [experiment guide](../../fruitfly_agent/experiments/README.md#use-completed-process-feedback)
shows how to enable it and separate exploration from official selection.

Edit model-role selections in `default-config.yaml`, execution values in
`components/H/execution-policy.yaml`, and search/feedback in their I component
files. `experiment.yaml` selects the baseline, task document and comparison,
grants changes and bounds the job. The [field guide](../../fruitfly_agent/experiments/CONFIGURATION.md)
describes the complete configuration tree. Refresh preparation after runtime changes.

| Evidence | Workspace location |
|---|---|
| Operation status, frozen configuration and links | `.fruitfly/experiments/runs/<id>/record.json` |
| Search plan, candidate executions, comparisons and result | Linked `.fruitfly/improvement/jobs/<job-id>/` |
| Benchmark reports, trials, Agent trajectory and verifier output | Linked `.fruitfly/eval/<evaluation-id>/` |
| Preparation receipts and caches | `.fruitfly/eval-cache/` and `.fruitfly/experiments/prepared/` |

Follow recorded links; a run can include several benchmark evaluations. Keep these
directories together. Failed/interrupted runs can have partial evidence; container
filesystems and Docker images are not complete archived copies of the experiment.

## Expand the material or choose another operation

Change the request's variant or exact task names, then repeat preparation and
checks. Before moving beyond smoke, choose bounded sampling and task concurrency
using the [joint template](multi-task.example.yaml). Multiple collections can
reference different registered benchmarks or installed native packs while sharing
one compatible baseline. Candidate parallelism currently stays at 1.

`eval prepare` prepares task-set collections. Fixed-version `eval run` instead
requires `task.source: eval` with `request`, `host` and optional `model_calls` at
the task level; it never starts Improvement. `rsi run` needs an independent
adoption verifier, which benchmark development rewards alone do not provide.
For a ready native holdout example, see the [Python function pack](../improvement/python_functions/README.md).
