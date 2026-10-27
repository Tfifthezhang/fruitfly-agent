# Experiment Files

[Up: Examples](../README.md)

Use one small experiment file and referenced component/task/comparison documents.
Read [the field guide](../../fruitfly_agent/experiments/CONFIGURATION.md) for the
schema and [component syntax](../../fruitfly_agent/runtime_spec/COMPONENTS.md) for
H/S/I files. All recipes use the same format without version markers.

| Recipe | Required material |
|---|---|
| [Native](native.example.yaml) | Generated system and [native task](tasks/native.yaml) |
| [Benchmark smoke](benchmark-smoke.example.yaml) | Prepared [Eval collection](tasks/tb4-smoke.yaml) |
| [Benchmark with execution edits](benchmark.example.yaml) | Same collection, explicit tool-limit grant |
| [Editor study](editor.example.yaml) | Installed [editor material](tasks/editor.yaml), disjoint private packages |
| [Multiple collections](multi-task.example.yaml) | Prepared requests/hosts referenced by [multi-task material](tasks/multi.yaml) |
| [TB4 request](tb4-smoke-request.example.json) | Benchmark smoke and the [Linux walkthrough](TB4_SERVER.md) |

These YAMLs reference additional files; copying one experiment alone is not a
complete workspace. Initialization writes the installed matching tree safely.

## Start a native experiment

Install using [Getting started](../../GETTING_STARTED.md#install), then run inside
an existing empty workspace:

```bash
fruitfly-agent-lab init
```

Edit `.fruitfly/models.yaml` for your account and place the key privately
in `secrets.env` or the process environment. Model declarations contain key
variable names only. Select aliases in `default-config.yaml`. Edit your task in
`.fruitfly/tasks/native.yaml`, and component values under `.fruitfly/components/`.

```bash
fruitfly-agent-lab improvement check
# Model requests and task execution; charges may apply.
fruitfly-agent-lab improvement run --events jsonl
fruitfly-agent-lab improvement list
fruitfly-agent-lab improvement report '<RUN_ID>' --json
```

The native instruction recipe has behavioral feedback and no independent holdout.
For measured search/RSI, install the [Python function pack](../improvement/python_functions/README.md#search-and-review)
and select it in the task document. Native file trials do not inherit a shell,
network tools or production files. Initialization preserves existing daily files,
regular model catalogs and secrets, rejects other config collisions and makes no
external requests. When a catalog already exists, select its actual aliases in
`default-config.yaml` before checking.

## Start a remote Linux benchmark experiment

Follow [TB4 setup](TB4_SERVER.md) for runtime installation and preparation:

```bash
fruitfly-agent-lab init --source task-set --benchmark terminal-bench-4
# Edit models/credentials and host Linux runtime path variables first.
fruitfly-agent-lab eval prepare --tasks-only
fruitfly-agent-lab eval prepare
fruitfly-agent-lab improvement check
# Models and official verification; charges may apply.
fruitfly-agent-lab improvement run --events jsonl
```

Initialization only reads the catalog. Preparation can download/build/start
containers but makes no task model calls. The host needs a complete Linux Python
and Agent venv; macOS paths are not usable Linux runtime inputs.

For fixed-version `eval run`, choose an Eval task document (`source: eval`,
`request`, `host`) instead of a collection. Neither operation starts RSI implicitly.
Benchmark development reward alone cannot authorize persistent adoption.

## Understand the files

```text
.fruitfly/
├── default-config.yaml        # Select models and H/S/I documents
├── models.yaml                # Shared daily and experiment model specifications
├── secrets.env
├── components/
│   ├── H/                     # Prompt, execution, environment, tools, context
│   ├── S/                     # Optional retained documents
│   └── I/                     # Editor, feedback and search
├── experiment.yaml            # Baseline, task reference, edit grants, budgets
├── comparison.yaml            # Fixed comparison conditions
├── tasks/                     # Task sources and material references
├── eval-request.json          # Optional benchmark request
└── eval-host.yaml             # Optional machine/runtime host
```

Only selected components need files. Model roles live in config, rounds in I
search, assessment in I feedback, tool limits in H execution, and permitted
changes in experiment. Paths resolve from the file that declares each reference.
Daily `.fruitfly/config.yaml` uses the same system schema and shared `models.yaml`.
Daily and baseline configs select their own model aliases and component documents.
Copying values does not keep different workspaces in sync.

## Read the complete reference

Use [the experiment field guide](../../fruitfly_agent/experiments/CONFIGURATION.md)
and [the component guide](../../fruitfly_agent/runtime_spec/COMPONENTS.md).
`benchmark.example.yaml` is a compact runnable recipe, not a duplicate catalog of
every field. [Comparison](comparison.yaml) and [task documents](tasks/native.yaml)
are independently editable. A component's own guide defines its parameter limits.

## Select models by role

Add catalog entries first, then select their case-sensitive aliases under the
selected profile in `default-config.yaml`:

```yaml
models:
  catalog: models.yaml
  roles:
    executor: your-executor-profile
    editor: your-editor-profile
    assessor: your-assessor-profile
```

The three names are placeholders for entries in the same catalog. The remote API
ID remains inside each catalog entry. Generated defaults use
`deepseek-flash-openai` for all three roles. Missing editor/assessor choices inherit
the executor. A declared unused I role does not create a client during ordinary
startup. Official benchmark grading is independent of the model assessor.

## Optimize shared candidates across tasks

Use [multiple collections](multi-task.example.yaml), configure its placeholder
request/host paths and select one shared baseline. Each collection retains its
objective, partitions and source identity. I search may configure `sampling` and
`promotion_every_rounds`; experiment `trial` controls concurrency and attempts.
Comparison owns aggregation and regression limits. Edit grants must be supported
by every selected execution backend. Default root totals scale with material;
explicit totals must fund initial probes and protected final selection.

`check --json` lists task keys, coverage, effective values and capabilities.
Use the actual keys for fixed sampling. Confirmation inputs remain private.
Candidate concurrency is one. See [task-set contracts](../../fruitfly_agent/lab/improvement/task_sets/README.md).
