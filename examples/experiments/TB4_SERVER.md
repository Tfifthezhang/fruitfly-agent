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
| `default-config.yaml` | Executor profile, enabled mechanisms and tool-call limit, initially 512 per turn |
| H/S/I groups in `default-config.yaml` | Registered defaults or explicit component documents; no copied components tree |
| `tasks/tb4-smoke.yaml` | Task material and fixed comparison rules |
| `experiment.yaml` | Baseline/task references, editable fields, fixed search/assessment settings and independent phase times |
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

The [smoke template](benchmark-smoke.example.yaml) is a research main file.
Its initial `next` selects one fixed baseline execution. `optimization` controls
legal editing scope; `stages` supplies independent phase settings.

## Execute one stage and inspect it

This command executes only `next.stage`; model/task work incurs charges:

```bash
"$FRUITFLY_LAB" --cwd "$FRUITFLY_EXPERIMENT" improvement show
"$FRUITFLY_LAB" --cwd "$FRUITFLY_EXPERIMENT" improvement step --events jsonl
"$FRUITFLY_LAB" --cwd "$FRUITFLY_EXPERIMENT" improvement inspect
"$FRUITFLY_LAB" --cwd "$FRUITFLY_EXPERIMENT" improvement report '<RUN_ID>' --json
```

Edit `next` to select organization, assessment, proposal, execution or comparison.
Consume the named outputs from `observed` or `references.json`. No phase runs
another phase automatically. Use Ctrl+C for cancellation and inspect uncertain
external effects before retrying. Scores remain observations and do not select
research continuation or authorize production activation.

| Evidence | Location under the configured research output root |
|---|---|
| Per-stage configuration and reports | `runs/<id>/` |
| Branch references and activity history | `references.json`, `research-events.jsonl` |
| Reading guides | `evidence/<id>/` |
| Full candidate configs and changes | `candidates/<id>/` |
| Execution batches and comparisons | `results/`, `comparisons/` |

Keep the complete root together for portable inputs. See the
[stage guide](../../fruitfly_agent/lab/improvement/DEVELOPER_GUIDE.md).

## Expand the material or choose another operation

Change the request's variant or exact task names, then repeat preparation and
checks. Before moving beyond smoke, choose task concurrency
using the [joint template](multi-task.example.yaml). Multiple collections can
reference different registered benchmarks while sharing
one compatible baseline. Candidate parallelism currently stays at 1.

`eval prepare` prepares task-set collections. Fixed-version `eval run` instead
requires `task.source: eval` with `request`, `host` and optional `model_calls` at
the task level; it never starts Improvement. Persistent adoption needs an independent
adoption verifier, which benchmark development rewards alone do not provide.
The [Python function pack](../improvement/python_functions/README.md) supplies holdout
material for embeddings with an explicitly registered task backend.
