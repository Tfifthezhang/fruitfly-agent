# Experiment Files

[Up: Examples](../README.md)

Copy one template to `.fruitfly/experiment.yaml` in the intended workspace only
when that destination is absent. Edit paths manually. The [experiment guide](../../fruitfly_agent/experiments/README.md)
defines fields, defaults, model roles and external effects.

| Template | Required material |
|---|---|
| [Native task](native.example.yaml) | Independent default Agent/model files and a configured credential |
| [Benchmark smoke task set](benchmark-smoke.example.yaml) | One prepared Eval collection; concurrency 1 and shared task-set evaluation |
| [TB4 smoke request](tb4-smoke-request.example.json) | Catalog selection paired with the smoke task-set template and [Linux walkthrough](TB4_SERVER.md) |
| [Complete reference / benchmark](benchmark.example.yaml) | Existing Eval request/host, Linux runtime and prepared task images; commented native/editor alternatives |
| [Editor](editor.example.yaml) | Installed `editor-study` manifest and its disjoint development/verification task packs |
| [Joint task sets](multi-task.example.yaml) | One or more prepared Eval collections or installed native task packs, sharing a baseline |

```bash
fruitfly-agent-lab improvement check
# Explicit model/task execution; may incur charges.
fruitfly-agent-lab improvement run
```

`check` makes no model requests. The benchmark template needs `eval prepare`
before execution; preparation can download/build/start environments. The editor
material ID is a placeholder, not a bundled dataset. Native tasks use detached
in-memory files, not a full local shell.

## Start a native experiment

Install the package using [Getting started](../../GETTING_STARTED.md#install).
Run in an existing empty workspace, using the installed CLI or its absolute path:

```bash
fruitfly-agent-lab init
```

Open `.fruitfly/default-models.yaml` and verify the model ID, protocol, endpoint
and token limits for your account. Put its `DEEPSEEK_API_KEY` value privately in
`.fruitfly/secrets.env`, or export it in the process environment. Replace the
instruction in `.fruitfly/experiment.yaml` with your material. Then:

```bash
fruitfly-agent-lab improvement check
# Model requests; may incur charges.
fruitfly-agent-lab improvement run --events jsonl
fruitfly-agent-lab improvement list
fruitfly-agent-lab improvement report '<RUN_ID>' --json
```

The minimal template exercises detached execution and candidate search with
behavioral feedback. It has no objective task score or independent holdout.
For scored comparison and verified RSI, install the [Python function pack](../improvement/python_functions/README.md#search-and-review)
and follow its configuration recipe. `rsi run` requires independent verification;
neither a plain instruction nor a benchmark development score supplies it.

`init` preserves daily configuration and an existing secret file, and rejects
existing experiment/default destinations. It does not read credentials, install
dependencies or execute tasks. Every generated setting remains a manually editable
file. The initializer uses installed copies of these public templates; offline
tests keep their contents synchronized.

## Start a remote Linux benchmark experiment

Follow the [TB4 walkthrough](TB4_SERVER.md) for a fresh server setup, the exact
smoke request, preparation, checks and Improvement. With the controller and Linux
Agent runtime already installed:

```bash
fruitfly-agent-lab init --source task-set --benchmark terminal-bench-4
# Edit models/credentials and export the two Linux runtime path variables first.
fruitfly-agent-lab eval prepare --tasks-only
fruitfly-agent-lab eval prepare
fruitfly-agent-lab improvement check
# Model requests and official verification; may incur charges.
fruitfly-agent-lab improvement run --events jsonl
```

The initialization command only looks up the benchmark descriptor. It does not
probe Docker or prepare tasks. `eval prepare` can download/build/start containers;
it makes no model requests. The generated host template uses
`FRUITFLY_EVAL_PYTHON_ROOT` and `FRUITFLY_EVAL_VENV`, which must point to a complete
Linux installation and an Agent venv. They are not macOS paths or model settings.

The generated task-set supports one task with concurrency 1. For larger selections,
review the [joint reference](multi-task.example.yaml) before changing sampling,
parallelism, budgets or collections. It uses the same scheduler and joint selection.
`eval prepare` supports task-set sources; fixed-version `eval run` requires the
single-request `task.source: eval` recipe rather than a task-set source.

## Understand the files

| File | Responsibility |
|---|---|
| `.fruitfly/experiment.yaml` | Select task source, search/evolution, completed-process assessment, exploration, role models or allocations |
| `.fruitfly/default-config.yaml` | Select the default Agent profile, executor model, execution tool limit, prompt and mechanisms |
| `.fruitfly/default-models.yaml` | Define named model entries: protocol, model ID, endpoint, capabilities, limits and credential variable |
| Benchmark request JSON | Select benchmark/variant, workspace, attempts, concurrency and timeout; optionally override the Agent configuration |
| Eval host YAML | Declare Linux runtime mounts, task directory, cache and dependency preparation |

For the benchmark template, `schema_version: 1` identifies the experiment format.
`task.source: eval` selects the optional benchmark executor. The `request` and
`host` paths resolve relative to the experiment YAML, so `../request.json` points
to the workspace root when the YAML is in `.fruitfly/`. Without an explicit
`runtime.config_path` in the request, Eval selects the workspace default Agent
configuration and that file's `default_profile`.

Defaults belong to the selected workspace, not a global project directory. A
checkout can have local defaults and each experiment workspace can have its own
copy. Editing one copy does not synchronize others. Templates under `examples/`
are the portable starting point; local configuration and credentials are not
distribution inputs.

## Read the complete reference

The [complete YAML reference](benchmark.example.yaml) lists every current
experiment field, its defaults, units, bounds and built-in choices. Its active
source is Eval. Replace the `task` section with a commented native or editor
recipe to use another source. Keep one definition of each key; uncommenting a
second `task`, `runtime` or stop-policy key without replacing the first is invalid.

| Notation | Meaning |
|---|---|
| Active value | Used on the next explicit run; search/evolution values match built-in defaults |
| `Choices: a \| b` | Supported alternatives; select one value |
| Commented component list item | Optional editable target; enable its owner and use a compatible runner |
| Commented replacement recipe | Disabled example; replace the corresponding active section to enable it |
| `null` stop policy | Use the built-in stopping behavior |
| Explicit state limitation | The condition requires evidence not supplied by that operation; do not assume it will trigger |

The reference includes all Improvement settings, RSI settings, model-role
references, task-source parameters, and each declarative stop-policy constructor.
Switching to editor material also requires replacing the component allowlist and
checking its larger allocation: explicit limits override source defaults. Material
size can require more than the suggested allowance.

Files retain separate responsibilities. Agent mechanisms and model specifications
stay in the default configuration/catalog. Task scorers, data splits and private
suite-use limits stay with their material. The YAML's final comments identify
these owners. Python extension ports are identified without adding unsupported
configuration keys. A declared RSI block never starts evolution by itself.

## Select models by role

First add usable entries to the model catalog referenced by the Agent profile.
Then select the executor through `profiles.<profile>.model.profile` in
`default-config.yaml`. Adding a catalog entry alone does not select it. Changing
the specification of an already selected entry affects subsequent runs.

Every template explicitly selects the editor and model-based assessor using the
`deepseek-flash-openai` entry in the default model template. Both currently use
the same underlying `deepseek-flash` model. Change either name to select another
existing catalog entry. For example:

```yaml
models:
  editor: your-editor-profile
  assessor: your-assessor-profile
```

Both names are placeholders for existing entries in the same model catalog, not
remote model IDs. Omitting either role inherits the executor unless an explicit
auxiliary choice is already declared by the Agent profile. Official benchmark
verification remains a task-owned program; `assessor` does not replace that
program and may be unused when the workflow uses only official scores.

Native tasks also support `models.executor` as a per-experiment override. Eval
sources select their executor through the Agent configuration referenced by the
request. Credential values stay in the workspace secret environment; catalogs
store variable names only. Check changed configuration before running; refresh
benchmark preparation when the check reports it invalid. Running jobs retain
their frozen configuration.

The current experiment `models` section accepts only `executor`, `editor` and
`assessor`. It does not configure a not-yet-installed subagent mechanism. Future
mechanisms must declare their own model references and dependencies through the
runtime's public assembly contracts instead of adding fields to Improvement.

## Optimize shared candidates across tasks

Use the [joint template](multi-task.example.yaml). `multi_task` owns sampling,
execution parallelism, score aggregation and promotion. Nondefault values require
`task.source: task-set`; the single-task settings remain compatible.
Source request paths, installed pack IDs and exact task names are placeholders.
Each collection keeps its own objective and private material. Adding an unrelated
benchmark name does not install an adapter.

`improvement check --json` lists generated task keys for fixed sampling, partitions,
collection coverage and the minimum allocation. All benchmark requests must share
the experiment workspace and Agent configuration/profile. `eval prepare` prepares
only the declared Eval sources; native sources need no containers. `eval run`
remains a fixed-version single-request benchmark operation.

Search evaluates common small batches, then compares promising candidates on the
complete shared selection set. Formal results are distinct from exploration seeds.
Default totals scale with declared per-task caps; explicit totals override them.
Candidate concurrency remains one. File packs preserve private validation/holdout;
confirmation inputs never enter editor evidence. See [Task sets](../../fruitfly_agent/lab/improvement/task_sets/README.md).
