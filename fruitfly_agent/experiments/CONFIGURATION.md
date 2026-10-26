# Write Experiment Configuration

[Up: Experiments](README.md)

A system config selects H/S/I values. An experiment selects that config, task
materials, permitted changes and fixed comparison conditions. Start with
[Component documents](../runtime_spec/COMPONENTS.md), then initialize a workspace
using the [examples](../../examples/experiments/README.md).

## Assemble an experiment

```yaml
schema_version: 2
baseline:
  config: default-config.yaml
  profile: baseline
tasks: {file: tasks/native.yaml}
comparison: {file: comparison.yaml}
edit:
  base_prompt:
    fields: [parameters.text]
budget:
  max_model_calls: 256
  max_executions: 16
  timeout_seconds: 3600
trial:
  operation_timeout_seconds: 1200
```

`baseline.config` resolves from the experiment file. `tasks` and `comparison`
accept exactly one `file` or `inline` reference. Their paths resolve from the
declaring file. Unknown/duplicate fields fail; there is no deep-merge inheritance.

| Section | Responsibility |
|---|---|
| `baseline` | One config/profile shared by every task collection |
| `tasks` | Source, instruction/files, installed package/editor material or collections |
| `comparison` | Feedback mode, task/persistent scope, aggregation and formal selection |
| `edit` | Explicit component fields and optional tighter bounds |
| `budget` | Hard search model/execution totals and deadline |
| `trial` | Task model allowance, operation timeout; task-set attempts/concurrency |
| `rsi` | Fixed cross-generation totals, verification policy and continuation |
| `stop` | Fixed search/evolution stopping recipes |

Keep strategy, rounds, editor instructions, evidence/assessment and model-role
values in the referenced system's I documents and model bindings. Editing those
files configures the next run; it does not grant candidate editing.

## Grant component changes

```yaml
edit:
  base_prompt:
    fields: [parameters.text]
  execution-policy:
    fields: [parameters.max_tool_calls_per_turn]
    bounds:
      parameters.max_tool_calls_per_turn: {minimum: 64, maximum: 256}
```

The initial value must fit the bounds. Fields come from registered owners, not
arbitrary YAML paths. An enabled component unsupported by the selected runner
cannot be edited. The editor receives `context/edit-grants.json`; the owner
enforces those grants again on every candidate.

| Target | Supported schema-2 grant |
|---|---|
| `base_prompt`, enabled `tool-guidance.<name>` | `parameters.text` |
| `execution-policy` | Declared scalar `parameters.*` fields and integer bounds |
| `execution-workflow` | `parameters.steps` |
| `learned-memory`, `skill-document` | `parameters.initial_text` |
| `improvement-editor` | `parameters.instructions.propose`, `invariant`, `domain`, `compose` |
| `improvement-feedback` | `parameters.evidence.page_characters`, `judgment_guidance`, `comparison_guidance`, `process_assessment.assessors` |
| `improvement-search` | `parameters.strategy`, `rounds`, `exploration` |

The I editor field names in the table share the `parameters.instructions.` prefix;
feedback/search names share `parameters.`. Numeric bounds apply only to supported
integer fields. Protected fields, models, root budgets, owners and roles cannot
be changed by these grants. General mechanism parameters are configurable;
candidate editing requires an explicitly registered adapter.

## Supply task and comparison documents

```yaml
# tasks/native.yaml
schema_version: 1
source: files
instruction: Produce a concise inventory of the supplied material.
input_paths: []
```

Replace instruction/files with `pack: your-installed-pack` for a package that
owns its inputs and scorer. That ID is a placeholder. Native execution provides
fresh in-memory file tools; it does not inherit Bash, network or production files.
File-task parameters support `assessment_interval` and `model_calls`.

```yaml
# comparison.yaml
schema_version: 1
scope: task
feedback: auto
aggregation: collection-macro
selection: all
minimum_gain: 0
max_collection_regression: null
adoption: none
```

`feedback` is `auto`, `behavior` or `scored`; scored feedback needs an actual
measurement source. `scope: persistent` still requires the execution's independent
verification policy. Keep `adoption: none`; activation is a separate host operation.
For task sets, `weights` maps collection IDs to positive weights. Final selection
uses all declared selection material and retains the incumbent on ties.

An Eval task document uses `source: eval`, `request` and `host`; a collection
document uses `source: task-set` and a nonempty `collections` list. Request/host
paths resolve from the task document, while Eval's working directory retains its
workspace-relative semantics. Existing request/host formats remain unchanged.

Task-set `trial.attempts` and `trial.concurrency` control the common scheduler;
leaf benchmark requests remain one-attempt, one-concurrent. `trial.model_calls`
sets each declared leaf allowance. Configure sampling and promotion frequency
under I search `sampling` and `promotion_every_rounds`. Those settings require a
task set and are not yet editable I fields in native paired episodes.

## Enable completed-process feedback

Edit the selected `improvement-feedback` document:

```yaml
parameters:
  evidence: {projection: granted-full, page_characters: 12000}
  process_assessment:
    assessors: [execution-facts-v1, completed-model-v1]
    model_role: assessor
    max_model_calls: 16
    timeout_seconds: 120
    required: false
```

Edit the selected `improvement-search` document:

```yaml
parameters:
  strategy: simple
  rounds: 2
  exploration: process-guided
```

These are parameter excerpts, not complete component envelopes.
`execution-facts-v1` projects counters without calling a model. `completed-model-v1`
uses `models.roles.assessor` for cited judgments. Optional `judgment_guidance` and
`comparison_guidance` add diagnosis instructions; receipt validation stays fixed.
Process-guided exploration chooses the next editing seed when another round runs.
It does not replace formal scoring or grant adoption. A one-round search has no
next seed. Model judgments consume the shared root allowance as well as the local
assessment sublimit. Optional unavailable judgments fall back; required ones stop.

Raw facts remain immutable. Character-page receipts record exactly what text the
editor received. Binary originals retain their existing visual/reader contracts.
Private verifier inputs and answers never enter the editing grant.

## Compare I candidates

Use `source: editor` with installed disjoint development/verification packages.
The [editor recipe](../../examples/experiments/editor.example.yaml) selects mutable
editor fields; substitute supported feedback/search grants to study those I
surfaces. An episode holds candidate I fixed while modifying H/S. Search rounds
must fit its fixed `inner_depth`; all nested calls spend the same outer budget.
Outer scoring, model bindings, acceptance thresholds and private material remain
fixed. Mixed outer H/S/I edits are rejected. Benchmark-backed I episodes and
benchmark RSI remain unavailable without an injected implementation.

## Inspect and retain a run

`improvement check --json` lists effective values, source documents, backend
capabilities and normalized edit bounds. Root and local allowances have different
scopes; raising a tool limit never raises a model allowance.

Inputs are frozen before execution and checked again before starting work.
Generated candidates contain ordinary schema-2 configs under
`.fruitfly/improvement/jobs/<job-id>/candidates/<id>/config.yaml`, with model
catalog and exact component content. `changes.json` retains parent and evidence.
The source baseline is not overwritten. Reused trials remain the same sample.

Existing schema-1 experiment files remain readable through their versioned
adapter; they retain their existing override behavior. New templates use schema 2.
There is one runtime assembler. See [Run configuration](../run/configuration/README.md)
for offline system inspection and explicit config export.
