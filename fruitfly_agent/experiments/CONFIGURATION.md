# Write Experiment Configuration

[Up: Experiments](README.md)

An experiment chooses a baseline, task material and authorized edits. Its runtime
conditions have four owners: execution, evidence, evaluation and stopping.
System H/S/I syntax belongs to the [runtime specification](../runtime_spec/COMPONENTS.md).

```yaml
baseline: {config: default-config.yaml, profile: baseline}
tasks: {file: tasks/tb4-smoke.yaml}
edit:
  working-memory-reduction:
    fields: [parameters.instructions.update, parameters.settings.memory_tokens]
    bounds:
      parameters.settings.memory_tokens: {minimum: 512, maximum: 4096}
execution:
  generator: agent-editor-v1
  editor_seconds: 1200
  task_seconds: 3600
  retain_experience: false
evidence:
  read: {default_characters: 12000, max_characters: 24000}
  catalog: {default_entries: 50, max_entries: 100}
  search: {default_matches: 20, max_matches: 50, max_characters: 12000}
evaluation:
  evaluator_seconds: 1200
  scope: task
stopping:
  max_rounds: 1
  no_improvement_rounds: 0
  consecutive_failures: 0
```

The baseline must enable each granted component and fit its bounds. Paths resolve
from the declaring file. `tasks` accepts exactly one `file` or `inline` reference.
Unknown fields and duplicate keys fail; there is one configuration grammar.
Model roles belong to the referenced system configuration.

| Section | Fields and meaning |
|---|---|
| `baseline` | `config`, optional `profile` |
| `tasks` | File instruction/inputs, installed package, I study or task collections |
| `edit` | Component IDs mapped to `fields` and optional numeric `bounds`; omission discovers supported default-selected surfaces |
| `execution` | Generator, editor/task seconds, direction and explicit experience retention |
| `evidence` | Shared read, directory and search limits; validated by the evidence module and injected into both roles |
| `evaluation` | Evaluator seconds, `scope: task|persistent` and optional task-set `comparison` |
| `stopping` | `max_rounds` (1–10); no-improvement/failure round limits (0 disables the condition) |
| `rsi` | Separate generation and independent activation conditions |

## Grant component changes

| Field category | Examples | Meaning |
|---|---|---|
| `parameters.instructions.*` | Base `system`, native tool `description`, Skill loading `usage`, task-memory `update`/`shrink`/`readback`, cross-session `reading`/`extraction`/`consolidation`, editor/evaluator prompts | Model-facing instructions |
| `parameters.settings.*` | Layered-compaction policy, working-memory sizes, Skill catalog `max_chars`, Bash default timeout | Owner-declared mutable parameters |
| `parameters.content.*` | Memory/Skill `documents` collections | Retained editable material |

`list_targets` pages a frozen target index. `describe_target` supplies field type,
meaning, current/default value, unit and constraints. Owner validation and the
experiment grant both apply. Models, permissions, schemas, source locations,
coverage bookkeeping, official objectives and private verification data remain
protected. Host execution conditions have no selectable component or optimization grant.

Tool parameters are available for explicit grants but excluded from automatic
selection. Native tools expose their complete H descriptions; individual
schemas, names, implementations and permissions remain protected.

Candidate execution requires a backend declaring the relevant capabilities,
including configuration materialization for working-memory parameters. The backend
owns fresh Session/history, resources, hooks, tools and isolation. `files` is a
material format, not a built-in executor; embeddings must register its runner. H/S and I cannot mix in one study.

## Supply task and comparison documents

Tasks use `source: files`, `eval`, `editor`, `registered` or `task-set`. See the
[recipes](../../examples/experiments/README.md). Task sets additionally accept
`execution.trial: {attempts: 1, concurrency: 1}`, `execution.sampling` and
`execution.promotion_every_rounds`. Candidate concurrency remains one.

`evaluation.comparison` accepts `minimum_gain`, `max_collection_regression`,
`aggregation: collection-macro|task-macro` and positive collection `weights`.
Incomplete shared selection coverage cannot produce joint utility. Persistent
publication requires independent verification and explicit host activation.

### Use an owner-registered learning execution

```yaml
tasks:
  inline:
    source: registered
    execution: memory-learning
    material: memory-study
    parameters:
      repetitions: 2
      min_gain: 0
      max_regression: 0
edit:
  file-memory:
    fields: [parameters.instructions.extraction]
evaluation:
  scope: persistent
```

`memory-study` is a placeholder installed study ID under
`.fruitfly/improvement/experiments/<id>/experiment.json`. Its manifest references
disjoint development and verification task packages compatible with `file-memory`.
Each package needs training inputs and private validation/holdout checks. See
[File memory](../lab/context_manager/augmentation/memory/methods/file_memory/README.md).
The execution owner declares roles, capabilities, material freezing, persistent
verification policy and runner requirements. The shared source consumes those
declarations. A study document supplies no task runner: an embedding must inject a
compatible isolated downstream backend. Check reports this limitation offline;
explicit execution may call models and does not activate production memory.

## Configure evaluation and evidence

One shared evaluator assesses the six default dimensions when applicable: quality,
reliability, resources, progress, verification and completion. It reads execution
facts and optional authoritative measurements. Unsupported or uncertain judgments
retain the incumbent; official scores are not rewritten by model opinion.
See [Assessment](../lab/improvement/assessment/README.md).

Evidence navigation has three layers: overview, event directory and originals.
Literal search and exact source-page citations share one
[evidence service](../lab/improvement/evidence/README.md). Cross-round indexes link
candidate hypotheses, receipts, assessments and selections; they do not copy facts
or grant assurance. Merely listing a source does not establish that it was read.

## Fix rounds and stopping

The fixed flow executes a baseline, generates zero or one candidate each round,
executes it, compares completed results and continues from the retained incumbent.
No candidate or a generator stop ends search. The default is one round,
`agent-editor-v1`, no retained experience. Other registered generators implement
the same proposal contract. I studies hold candidate I fixed during fresh inner
H/S searches and compare downstream behavior independently.

## Inspect and retain results

`improvement check --json` reports resolved values, source hashes, backend
capabilities and edit bounds without model calls. Candidate bundles live under
`.fruitfly/improvement/jobs/<job-id>/candidates/<id>/`. Generation preserves source
component files and daily defaults. Experience retention stages attributed lessons
for explicit review; it does not automatically change S.

Each editor, task and evaluator invocation has an independent positive finite
time. Nested calls in the same invocation share its clock. Composite studies
use leaf clocks. Improvement observes requests, tools and reported tokens without
count quotas. Daily Core execution separately defaults to 512 tool calls per turn.
Cancellation covers the job; unconfirmed cleanup stops scheduling. Offline fake
Providers establish covered behavior, not real quality gains.
