# Experiment Files

[Up: Examples](../README.md)

Use one small experiment file and referenced component/task documents.
Read [the field guide](../../fruitfly_agent/experiments/CONFIGURATION.md) for the
schema and [component syntax](../../fruitfly_agent/runtime_spec/COMPONENTS.md) for
H/S/I files. All recipes use the same format without version markers.

| Recipe | Required material |
|---|---|
| [Benchmark smoke](benchmark-smoke.example.yaml) | Prepared [Eval collection](tasks/tb4-smoke.yaml) |
| [Benchmark with prompt edits](benchmark.example.yaml) | Same collection, explicit prompt grant |
| [Editor study](editor.example.yaml) | Embedding with registered backend, [editor material](tasks/editor.yaml) and disjoint private packages |
| [Multiple collections](multi-task.example.yaml) | Prepared requests/hosts referenced by [multi-task material](tasks/multi.yaml) |
| [TB4 request](tb4-smoke-request.example.json) | Benchmark smoke and the [Linux walkthrough](TB4_SERVER.md) |

These YAMLs reference additional files; copying one experiment alone is not a
complete workspace. Initialization writes the installed matching tree safely.

## Initialize system configuration

Run inside an existing workspace:

```bash
fruitfly-agent-lab init
```

This generates the system/model/component files and an empty-key secret file.
It makes no external requests and does not generate an experiment or task executor.
Existing regular model catalogs and secrets are preserved; other destinations
must not exist. Choose actual model aliases from the shared catalog.

For task execution, use the benchmark recipe below or an embedding that explicitly
registers [TaskRunner/episode ports](../../fruitfly_agent/lab/improvement/execution/README.md).
The `files` material format and editor-study YAML do not supply a backend. CLI
checks report these sources unavailable and execution stops before model work.

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
│   └── I/                     # Editor and evaluator prompts
├── experiment.yaml            # Baseline, task reference, optional edit narrowing, phase times
├── tasks/                     # Task sources and material references
├── eval-request.json          # Optional benchmark request
└── eval-host.yaml             # Optional machine/runtime host
```

Only selected components need files. Model roles live in config; experiment
`execution`, `evidence`, `evaluation` and `stopping` group fixed experiment
conditions. Daily execution limits live in H execution and are not optimization targets. Paths resolve from the file that declares each reference.
Daily `.fruitfly/config.yaml` uses the same system schema and shared `models.yaml`.
Daily and baseline configs select their own model aliases and component documents.
Copying values does not keep different workspaces in sync.

## Read the complete reference

Use [the experiment field guide](../../fruitfly_agent/experiments/CONFIGURATION.md)
and [the component guide](../../fruitfly_agent/runtime_spec/COMPONENTS.md).
`benchmark.example.yaml` is a compact runnable recipe, not a duplicate catalog of
every field. Evaluation conditions and [task documents](tasks/tb4-smoke.yaml) are independently editable. A component's own guide defines its parameter limits.

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
objective, partitions and source identity. Experiment `execution` owns sampling/promotion scheduling and `trial`
attempts/concurrency. `evaluation.comparison` owns aggregation and regression limits. Edit grants must be supported
by every selected execution backend. Each editor, leaf execution and evaluator starts its own configured phase clock. Usage is observed without count quotas.

`check --json` lists task keys, coverage, effective values and capabilities.
Use the actual keys for fixed sampling. Confirmation inputs remain private.
Candidate concurrency is one. See [task-set contracts](../../fruitfly_agent/lab/improvement/task_sets/README.md).

## Navigate evidence across rounds

`evidence` defines shared read/catalog/search limits. Overview and event indexes
lead to originals; a cross-round index links hypotheses, receipts, assessments
and retained selections without a second ledger. Set `stopping.max_rounds` and
optional no-improvement/failure round limits in the experiment.

For command deliverables, an embedding must explicitly supply a delivery backend
and a frozen `delivery_manifest` input, in addition to the task runner. See [delivery admission](../../fruitfly_agent/lab/improvement/execution/README.md#validate-declared-task-outputs)
for the manifest contract and [clean-directory limits](../../fruitfly_agent/lab/improvement/verification/README.md#validate-delivery-bundles).
