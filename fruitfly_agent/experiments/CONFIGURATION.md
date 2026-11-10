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
| `baseline.config`, optional `profile` | Complete system configuration with H/S/I references and `models.roles` |
| `stages.<stage>.inputs`, `context` | Explicit named materials and supplementary context |
| `stages.<stage>.allowance` | Independent time and evidence supply allowance |
| `stages.propose.optimization` | Owner-validated default/explicit field grants |
| `stages.<stage>.publish_as`, `attempt` | Immutable output alias and reuse/retry decision |
| `next.stage` | Execute exactly one configured stage |

All configured stage syntax is validated. Only the selected stage resolves its
material references and requires backend preparation. Future-stage output aliases
may remain unavailable until explicitly produced. Configuration loading starts no
models or containers. Unknown fields fail; there is one current grammar.

Model aliases belong only to system `models.roles`; algorithm instructions and
settings belong to referenced component files. Research files do not accept
`roles`, profile `overrides`, top-level `optimization`, `evidence` or `observed`.
Results and recent history live under the output root, never in authored YAML.

## Select the next operation

```yaml
stages:
  propose:
    inputs:
      harness: {candidate: candidate-a}
      batches: [{artifact: candidate-a-results}]
      evidence: [{artifact: candidate-a-evidence}]
    direction: Improve attributable behavior using these observations.
    allowance:
      seconds: 1200
      evidence_characters: 256000
      evidence_responses: 64
    optimization:
      scope: defaults
      include: {}
      exclude: []
    publish_as: candidate-b
    attempt: reuse
next:
  stage: propose
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

| Stage | Controls | Allowance |
|---|---|---|
| `import` | `source: eval|batch`, `path`, optional `related_records`, `task_names`, `evidence_paths` | None; offline |
| `eval` | `tasks` | `task_seconds` |
| `organize` | `instruction` | `seconds`, `evidence_characters`, `evidence_responses` |
| `assess` | Input batches | Same reading allowance |
| `propose` | `direction`, `optimization` | Same reading allowance |
| `execute` | `tasks`, task-set `attempts`, `concurrency` | `task_seconds` |
| `compare` | At least two batches | Same reading allowance |

All stages also admit `inputs`, `context`, `publish_as` and `attempt`. A proposal
without a harness input uses `baseline`; execute requires an explicit harness.
`seconds` is the whole role invocation time, including format repair. Evidence
allowances are stage-local; omitted values use the shared evidence defaults.
`evidence_responses` bounds response supply, while character limits bound content.
The registered generator remains an execution capability, not another prompt or
model binding in this document.

A task reference uses exactly one `file` or `inline` document. Supported material
sources are owned by their registered backend. Import/organize/assess/propose/compare
do not require task containers. Execute/Eval require their backend and preparation.
All relative paths resolve from the main document.

## Inspect configuration before models

```bash
fruitfly-agent-lab improvement show --config .fruitfly/improvement.yaml
fruitfly-agent-lab improvement check --config .fruitfly/improvement.yaml
fruitfly-agent-lab improvement defaults --config .fruitfly/improvement.yaml
```

Show includes the current component configuration table; defaults expands legal
owner edit fields. Each proposal retains `configuration/optimization.json` and
`optimization.md` before its Editor Provider is constructed.

`stages.propose.optimization` controls editing. Default scope includes enabled supported owners except File memory and the three
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
```

Import is offline. Unknown, private, missing, changed and unsafe source paths fail;
only requested originals are frozen into the new batch. Other originals remain
external, including after portable bundle export. `source: batch` retains its
existing supplied batch and does not recollect Eval evidence. Evidence allowance settings are
positive integers; [Lab evidence](../lab/improvement/evidence/README.md#bound-an-investigation)
owns their execution semantics. Do not add configuration version fields.

The default Improvement entry is `.fruitfly/improvement.yaml`; `--config` overrides
it. Stage controls are study intent, not another home for algorithm instructions.
Keep algorithm instructions in the referenced H/S/I component owner documents.
