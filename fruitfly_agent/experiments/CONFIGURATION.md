# Write Experiment Configuration

[Up: Experiments](README.md)

A system config selects H/S/I values. An experiment selects that config, task
materials, permitted changes and fixed comparison conditions. Start with
[Component documents](../runtime_spec/COMPONENTS.md), then initialize a workspace
using the [examples](../../examples/experiments/README.md).

## Assemble an experiment

```yaml
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

The baseline and daily system configs normally reference the same workspace
`models.yaml`. Each config selects its own `models.roles` aliases. Model definitions
belong in the shared catalog; experiment sections do not override them. Candidates
freeze the selected definitions for their executions.

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

| Target | Supported field grant |
|---|---|
| `base_prompt`, enabled `tool-guidance.<name>` | `parameters.text` |
| `execution-policy` | Declared scalar `parameters.*` fields and integer bounds |
| `execution-workflow` | `parameters.steps` |
| `learned-memory`, `skill-document` | `parameters.initial_text` |
| `improvement-editor` | `parameters.instructions.propose`, `invariant`, `domain`, `compose`; `parameters.max_tool_calls`, `parameters.max_turns` |
| `improvement-feedback` | `parameters.evidence.page_characters`, `evidence.access_mode`, `evidence.projection`, `judgment_guidance`, `comparison_guidance`, `process_assessment.assessors` |
| Enabled Bash, reduction, measurement, Web and IPython owners | Owner-declared `parameters.<field>` whitelist; numeric bounds; compatible materializing backend required |
| `improvement-search` | `parameters.strategy`, `rounds`, `exploration`; `research.enabled`, `research.max_entries`, `research.retrieve_entries`, `research.guidance`; `progress.patience`, `progress.failure_patience`; `finalization.reserve_model_calls`, `finalization.reserve_executions` |

Instruction field names share the `parameters.instructions.` prefix; editor
allowances and feedback/search fields share `parameters.`. Editor allowances
accept integer bounds; mechanism adapters accept the declared numeric field types. Protected fields, models, root budgets, owners and roles cannot
be changed by these grants. General mechanism parameters are configurable;
candidate editing requires an explicitly registered adapter.

## Supply task and comparison documents

```yaml
# tasks/native.yaml
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
Generated candidates contain ordinary component configs under
`.fruitfly/improvement/jobs/<job-id>/candidates/<id>/config.yaml`, with model
catalog and exact component content. `changes.json` retains parent and evidence.
The source baseline is not overwritten. Reused trials remain the same sample.

There is one experiment format and one runtime assembler. Unknown fields and
configuration version markers fail validation. See [Run configuration](../run/configuration/README.md)
for offline system inspection and explicit config export.

Research, progress and finalization fields share the `parameters.` prefix. Their
[owner](../lab/improvement/research/README.md#configure-and-compare-mechanisms) defines
strict defaults and runtime effects. Select I comparison execution to edit them;
ordinary H/S search may use the configured mechanisms but cannot edit its own I.
Integer fields support narrowing experiment bounds. Fixed root budgets and
verification rules are outside these grants.

## Optimize context policy

Enabled `compaction`, `working-memory-reduction` and `context-measurement`
components expose owner-validated H parameters. The two reduction methods expose
prompt text from their initial implementation. Grant fields explicitly through
`parameters.<field>` and optional numeric bounds; use an execution backend with
`configuration-materialization`. See [reduction ownership](../lab/context_manager/reduction/README.md)
and [measurement precision](../lab/context_manager/measurement/README.md) for the
mutable and protected fields. [Configuration examples](../../examples/configuration/README.md#select-reduction-and-measurement)
show method selection and a bounded memory-policy grant.

Stateful task memory is reset in each isolated trial. A same-Session policy
change reprocesses canonical evidence with the new policy identity. Coverage,
artifact hashes, Provider continuation, permissions and root budgets cannot be
edited. Method selection is an ordinary configuration choice; parameter grants
do not authorize changing component identity or silently enabling another method.
