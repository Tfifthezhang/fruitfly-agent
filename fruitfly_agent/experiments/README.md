# Experiments

[Up: Runtime Architecture](../README.md)

Run fixed-version Eval, Improvement and RSI independently of chat. System config
selects H/S/I; an experiment selects tasks, edit grants and fixed comparison
conditions. Daily, baseline and candidate configs use the same runtime assembler.

## Configure a workspace

```bash
fruitfly-agent-lab init
# Optional benchmark recipe; no model, download or container starts here.
fruitfly-agent-lab --cwd /path/to/workspace init --source task-set --benchmark terminal-bench-4
```

The workspace must already exist. Initialization creates a
`default-config.yaml`, referenced `components/H/` and `components/I/` documents,
`models.yaml`, `experiment.yaml`, `comparison.yaml`, a task document and an
empty-key `secrets.env` under `.fruitfly/`. Benchmark recipes add request/host
files. No empty S documents are created. Existing regular `models.yaml` and
secret files are reused unchanged; other existing destinations cause an error.
The daily config stays untouched. New files use 0600
and new directories use 0700. Ordinary write failures clean up only new files.

Edit model specifications and credentials before checking. Native initialization
works without Eval. See [native setup](../../examples/experiments/README.md#start-a-native-experiment)
and [remote TB4 setup](../../examples/experiments/TB4_SERVER.md).

The configuration guide tree is:

- [Configuration overview](../../CONFIGURATION.md): file responsibilities and precedence.
- [Component documents](../runtime_spec/COMPONENTS.md): write a system and its H/S/I files.
- [Experiment configuration](CONFIGURATION.md): tasks, grants, comparisons and budgets.
- [Component registration](../lab/catalog/CONFIGURATION.md): expose a new implementation.
- [Runnable recipes](../../examples/experiments/README.md): initialize, check and execute.

`--cwd` selects a workspace. `--config` selects an experiment file. Paths resolve
from their declaring documents. Explicit missing files, unknown fields and
duplicate YAML keys fail. Only the baseline/tasks/comparison/edit format is accepted; obsolete flat
experiment sections and configuration version markers are rejected.

## Choose operation and source

| Operation | Actions | Responsibility |
|---|---|---|
| `eval` | `catalog`, `prepare`, `check`, `run`, `list`, `report ID`, `stop ID` | Fixed-version benchmark execution |
| `improvement` | `check`, `run`, `list`, `report ID`, `stop ID` | Generate and compare changes |
| `rsi` | `check`, `run`, `list`, `report ID`, `stop ID`, `resume ID` | Independently verify, adopt and continue |

| Task source | Required material |
|---|---|
| `files` | Instruction/files or an installed task package |
| `task-set` | Collections of registered native/Eval sources |
| `editor` | Installed disjoint editor-study episodes |
| `eval` | Prepared benchmark request and host |

Task source declarations live in the document referenced by `tasks`. Native file
execution uses isolated in-memory file tools, without Bash, network or the live
Session. Ordinary conversations do not automatically create training material.
Eval is optional; `eval run` never starts improvement. Benchmark reward alone
cannot grant persistent adoption or RSI.

## Override only what matters

Start from the generated tree and edit the responsible file:

| Change | File |
|---|---|
| Available model definitions and Provider parameters | Shared `models.yaml` |
| Model roles or selected components | `default-config.yaml` |
| Prompt/tool/workflow/execution values | Referenced H component |
| Retained memory or Skill | Referenced S component |
| Editor instructions | Referenced I editor component |
| Process assessment and evidence presentation | Referenced I feedback component |
| Strategy, rounds, sampling and next-seed policy | Referenced I search component |
| Editable fields, root budget and task allowance | `experiment.yaml` |
| Formal comparison/assurance | `comparison.yaml` |
| Task source and material | Referenced task document |

Do not copy component values into experiment sections. See the complete
[field guide](CONFIGURATION.md) rather than maintaining a second field list here.
CLI choices do not activate arbitrary Python or install plugins.

## Enable completed-process feedback

Configure `process_assessment.assessors` in I feedback and `exploration` in I
search. [The field guide](CONFIGURATION.md#enable-completed-process-feedback)
contains complete parameter excerpts and model/cost rules. Use at least two
rounds for a next-seed decision. Official selection remains separate.

Raw execution facts remain immutable. Optional model judgments use the assessor
role and root allowance. Their local cap does not reset the root. Required
unavailable assessment stops the search; optional failure retains the incumbent.
Online file-task assessment is a separate explicit execution parameter.

## Prepare benchmarks

```bash
# Downloads/builds/containers may occur; no task model requests.
fruitfly-agent-lab eval prepare --tasks-only
fruitfly-agent-lab eval prepare
fruitfly-agent-lab improvement check
# Explicit model/task execution; charges may apply.
fruitfly-agent-lab improvement run
```

The adapter derives a bounded host from the trial model allowance. Original host
files stay unchanged. Preparation must match current runtime source and frozen
inputs. Checks never silently prepare, download or launch task containers.
All collections share one baseline and workspace; conflicting explicit request
references fail. See [Eval](../../eval/README.md) and its
[Improvement adapter](../../eval/improvement/README.md).

## Inspect records and stop safely

```bash
fruitfly-agent-lab improvement check --json
fruitfly-agent-lab improvement list
fruitfly-agent-lab improvement report '<RUN_ID>' --json
fruitfly-agent-lab improvement stop '<RUN_ID>'
fruitfly-agent-lab rsi resume '<RUN_ID>'
```

Use actual run IDs. `check` constructs no Providers and makes no model request.
It validates sources, model aliases, credential presence, capabilities and
applicable budgets; external connectivity and quality remain unverified.

Run indexes stay in `.fruitfly/experiments/runs/<id>/`. Journals and trials stay
in `.fruitfly/improvement/jobs/<job-id>/`; each generated candidate has an
ordinary config under `candidates/<id>/config.yaml` there. Models and component
contents are frozen with the candidate; source defaults stay unchanged. Follow
recorded links to Eval and independent verification evidence.

The host owns scoped cancellation and cleanup. Resume restores durable budget
usage/deadlines, does not replay uncertain paid work and reconciles activation.
One process owns each run. A selected output is not independent verification.

`--events jsonl` reports lifecycle/search events. Exit 0 means command completion,
1 incomplete execution, 2 configuration error, 3 blocked execution and 130
interruption; these are not quality certificates.

## Files and offline checks

| Files | Responsibility |
|---|---|
| `configuration.py`, `comparison.py` | Strict experiment parsing and fixed condition resolution |
| `sources.py`, `task_sets.py`, `policies.py` | Public task, batch and stopping composition |
| `composition.py`, `validation.py` | Shared runtime staging, backend checks and grants |
| `scaffolding.py`, `templates/` | Experiment-specific inputs; shared system templates belong to Run |
| `operations/`, `records.py` | Explicit execution, indexes, locks and scoped stop |
| `cli.py`, `menu.py`, `presentation.py` | Arguments and views |

```bash
.venv/bin/python -m unittest discover -s tests/experiments -t .
```

Tests use fake Providers/executors and temporary files, without model fees or
containers. Installed templates are checked outside the source checkout.

## Optimize a shared task set

Use the [multi-collection recipe](../../examples/experiments/multi-task.example.yaml).
Task documents preserve collection objectives and private partitions. I search
owns sampling/promotion scheduling; fixed comparison owns aggregation/regression
rules; `trial` owns attempts/concurrency. Candidate concurrency remains one.

Each leaf is an attributable execution. Shared-batch exploration and complete
selection remain separate; incomplete coverage cannot win. Root allowances
scale with material when omitted. Task-set search currently requires simple,
scored, task scope without experience retention. Independent adoption needs a
separately implemented policy.

## Check one resolved harness

Text/JSON checks show selected components, owner/source, effective values,
registered capabilities and edit bounds. Enabled, configurable and editable have
different meanings. New components must follow [Catalog admission](../lab/catalog/CONFIGURATION.md).
No host branch or hidden import may substitute for registration.
