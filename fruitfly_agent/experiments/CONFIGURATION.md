# Write Experiment Configuration

[Up: Experiments](README.md)

System configuration selects H/S/I components. An experiment selects task material,
authorized edits and comparison conditions. See [component syntax](../runtime_spec/COMPONENTS.md).

```yaml
baseline: {config: default-config.yaml, profile: baseline}
tasks: {file: tasks/native.yaml}
comparison: {file: comparison.yaml}
timeouts: {editor_seconds: 1200, execution_seconds: 3600, evaluator_seconds: 1200}
trial: {attempts: 1, concurrency: 2}
search: {strategy: simple, rounds: 1}
```

Paths resolve from the declaring file. `tasks` and `comparison` accept exactly
one `file` or `inline` reference. Unknown fields and duplicate keys fail. Model
roles belong to the referenced system configuration.

| Section | Responsibility |
|---|---|
| `baseline` | System configuration and profile |
| `tasks` | Files, installed task package, I study or task collections |
| `comparison` | Scope, feedback, aggregation, gain and collection regression rules |
| `edit` | Optional narrowing of automatically discovered legal targets and fields |
| `timeouts` | Independent positive finite seconds for each editor, execution and evaluator invocation |
| `trial` | Task-set attempts and task concurrency |
| `search` | Strategy, generator, rounds, mode, width, exploration, retention, sampling, research and progress |
| `assessment.evidence` | Evidence response page size (`page_characters`, default 12000) |
| `rsi`, `stop` | Generation conditions and stopping policies |

## Grant component changes

Omitting `edit` discovers all targets supported by the selected backend, H/S or I
study, and task material. Component registration provides the owner metadata and
default legal fields. An explicit `edit` narrows this scope:

```yaml
edit:
  working-memory-reduction:
    fields: [parameters.instructions.update, parameters.settings.memory_tokens]
    bounds:
      parameters.settings.memory_tokens: {minimum: 512, maximum: 4096}
```

This example requires a backend capable of materializing working memory.
The baseline must contain the target and fit every bound. Native in-memory
file execution cannot install context or shell mechanisms. H/S and I cannot mix
in the same study. A dedicated I study can grant evaluator prompts:

```yaml
edit:
  improvement-evaluator:
    fields: [parameters.instructions.criteria, parameters.instructions.compare]
```

| Category | Examples | Meaning |
|---|---|---|
| `parameters.instructions.*` | Base `system`, tool guidance `usage`, memory `update`/`shrink`, editor/evaluator prompts | Model-facing instructions |
| `parameters.settings.*` | Working-memory sizes, tool timeouts, execution parallelism, history artifact size | Owner-declared algorithm and runtime settings |
| `parameters.content.*` | Retained Skill `body`; registered multi-file `documents` | Retained editable material |

The same canonical paths appear in owner descriptions, grants and validation.
`list_targets` pages a frozen target index; `describe_target` loads field meaning,
type, current/default value, unit, choices, bounds and constraints on demand.
`context/edit-grants.json` retains the exact experiment scope. The initial editor
context does not contain every parameter description. Metadata, values and grants
contribute to frozen conditions. Owners revalidate every candidate.

Models, schemas, credentials, permissions, official objectives and private
verification material are protected. Improvement imposes no model-request,
tool-call, turn-count or cumulative token quota. Ordinary daily Agent execution
may explicitly configure its separate Core count limits.

## Supply task and comparison documents

Native tasks use `source: files`, `instruction` and optional `input_paths`, or an
installed `pack` ID. Eval tasks use `source: eval`, `request` and `host`. Task sets
use `source: task-set` and `collections`. I studies use `source: editor` and
disjoint installed study material. See [recipes](../../examples/experiments/README.md).

Comparison accepts `scope: task|persistent`, `feedback: auto|behavior|scored`,
`selection: all`, `adoption: none`, `minimum_gain`, `max_collection_regression`,
`aggregation: collection-macro|task-macro` and positive collection `weights`.
Scored feedback requires a measurement source. Incomplete shared selection
coverage cannot produce joint utility. Persistent adoption requires independent
verification and a separate host activation operation.

## Configure assessment and exploration

```yaml
assessment:
  evidence: {page_characters: 12000}
search:
  strategy: simple
  rounds: 2
  exploration: process-guided
```

One model evaluator assesses completed runs and compares candidates. Its prompts
define quality, reliability, resources, progress, verification and completion
criteria. Results contain dimensions, process signals, behavior-hypothesis checks,
optimization directions, uncertainty and supplied evidence citations. Official
scores stay separate. Equal scores can use supported process comparison; missing
or uncertain judgments retain the incumbent. `exploration: incumbent` is the default.
See [Assessment](../lab/improvement/assessment/README.md).

Evidence tools navigate deterministic overview, event index and original records.
Search is literal, cross-file and paginated. Each returned source span has its own
citation ID. Index listings do not make unread originals available as proof.

## Fix scheduling and research conditions

Defaults select `simple`, `agent-editor-v1`, one round, parallel mode, width 1 and
no experience retention. Simple requires width 1. `harness2` supplies the optional
parallel/sequential schedule. Task sets require simple/scored/task operation.
`search.sampling` and `search.promotion_every_rounds` control task-set scheduling.
[Research](../lab/improvement/research/README.md#configure-and-compare-mechanisms)
owns strict research/progress configuration. I studies hold candidate I fixed
inside fresh H/S searches, then compare downstream behavior independently.

## Inspect and retain results

`improvement check --json` reports resolved values, source hashes, capabilities
and edit bounds without model calls. Candidate configurations live under
`.fruitfly/improvement/jobs/<job-id>/candidates/<id>/` with component content, model
catalog and evidence references. The source baseline remains unchanged. Counts,
reported token usage, role and elapsed phase time are observations, not admission
controls. Missing usage remains explicit.

Each phase starts its own clock. Nested calls within the same invocation share
its clock. Composite task sets and I studies delegate timing to leaf phases.
A phase timeout does not cancel future phases; user cancellation covers the job.
Unconfirmed cleanup stops further scheduling. Reused receipts remain the same sample.
