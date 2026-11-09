# Configure Independent Research

[Up: Experiments](README.md)

Use one editable research document for historical configuration summaries and the
explicitly selected next operation. The complete field responsibilities and
examples belong to the [Improvement developer guide](../lab/improvement/DEVELOPER_GUIDE.md).
System component syntax belongs to [Runtime specification](../runtime_spec/COMPONENTS.md);
owner admission belongs to [Catalog](../lab/catalog/CONFIGURATION.md).

| Control | Meaning |
|---|---|
| `research.id`, `output_root`, `branch` | Study storage and branch-local reference lookup |
| `research.history_entries` | Generated recent-history/reference display length; default 10; full records remain on disk |
| `baseline.config`, optional `profile` | Original complete system configuration |
| `roles` | Executor, organizer, assessor and editor aliases from the model catalog |
| `overrides` | Ordinary profile mapping changes applied to the selected complete system |
| `optimization.scope` | `defaults` or `explicit` |
| `optimization.include` | Owner IDs with `fields` and optional numeric `bounds` |
| `optimization.exclude` | Owner IDs removed from the edit scope |
| `stages` | Parameters for each separately invoked stage |
| `evidence` | Shared read/catalog/search limits and cumulative `supply.max_characters` / `supply.max_pages` |
| `next` | One stage, named inputs, context, attempt and optional immutable output alias |
| `observed` | Generated projection; ignored for execution |

Only the selected stage's required inputs and settings are resolved. Config changes
never rewrite producer snapshots or require rerunning earlier stages. A required
missing/corrupt artifact prevents that operation, while other outputs remain usable.

## Select the next operation

```yaml
next:
  stage: propose
  publish_as: candidate-b
  inputs:
    harness: {candidate: candidate-a}
    batches: [{artifact: candidate-a-results}]
    evidence: [{artifact: candidate-a-evidence}]
  context: []
  attempt: reuse
```

`artifact` selects a branch-local named bundle. `candidate` selects a complete
candidate; `bundle` names an explicit portable bundle path. `config` is an explicit
system file for a harness input, including initial fixed execution. No latest,
score ranking or filesystem ordering selects a research origin.

`reuse` permits identical completed-activity reuse; `fresh` requests another
attempt; `retry-unresolved` explicitly authorizes retry after uncertain work.
A different result does not overwrite an existing output alias. Full reports remain
retained even if projection/alias publication needs attention.

## Configure stage settings

| Stage | Parameters |
|---|---|
| `import` | `source: eval|batch`, `path`, optional `related_records`, `task_names`, `evidence_paths` |
| `eval` | `tasks`, `task_seconds`; fixed prepared benchmark execution |
| `organize` | `timeout_seconds`, `instruction` |
| `assess` | `timeout_seconds` |
| `propose` | `timeout_seconds`, `generator`, `direction` |
| `execute` | `tasks`, `task_seconds`, task-set `attempts` and `concurrency` |
| `compare` | `timeout_seconds` |

A task reference uses exactly one `file` or `inline` document. Supported material
sources are owned by their registered backend. Import/organize/assess/propose/compare
do not require task containers. Execute/Eval require their backend and preparation.
All relative paths resolve from the main document.

## Inspect configuration before models

```bash
fruitfly-agent-lab improvement show --config experiment.yaml
fruitfly-agent-lab improvement check --config experiment.yaml
fruitfly-agent-lab improvement defaults --config experiment.yaml
```

Show includes the current component configuration table; defaults expands legal
owner edit fields. Each proposal retains `configuration/optimization.json` and
`optimization.md` before its Editor Provider is constructed.

Default scope includes enabled supported owners except File memory and the three
I roles. Memory/Skill libraries remain included. Include grants replace that owner's
field scope; explicit scope starts empty; exclude removes an owner. Protected and
mode-dependent fields still use owner validators. Permission to edit a mechanism
does not enable it or authorize production activation.

## Use fixed execution documents

Fixed Eval and advanced explicit bundle consumers also accept the common
`baseline`, `tasks`, `edit`, `execution`, `evidence` and `evaluation` sections.
These project through the same system loader and owner validators. They do not
provide stopping rounds, automatic promotion or automatic RSI composition.
A nonempty `edit` explicitly replaces the default scope in this direct projection.
Use the research main file for normal staged work.

## Select imported evidence

Eval import defaults to compact materials. `stages.import.task_names` is a list
of exact retained task names. `evidence_paths` maps permitted archive-relative
file paths to their recorded `sha256:` identities. Copy both from the source
catalog in `diagnostics/reading-scope.json`; placeholders below must be replaced:

```yaml
stages:
  import:
    source: eval
    path: /path/to/completed-eval
    task_names: [example-task]
    evidence_paths:
      artifacts/harbor/JOB/TRIAL/artifacts/answer.txt: "sha256:REPLACE_WITH_64_HEX_DIGITS"
evidence:
  supply:
    max_characters: 256000
    max_pages: 64
```

Import is offline. Unknown, private, missing, changed and unsafe source paths fail;
only requested originals are frozen into the new batch. Other originals remain
external, including after portable bundle export. `source: batch` retains its
existing supplied batch and does not recollect Eval evidence. Supply settings are
positive integers; [Lab evidence](../lab/improvement/evidence/README.md#bound-an-investigation)
owns their execution semantics. Do not add configuration version fields.
