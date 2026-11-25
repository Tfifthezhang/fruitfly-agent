# Investigate a large retained batch

[Up: Experiments](../README.md)

Use [improvement.example.yaml](improvement.example.yaml) with an explicit retained
Eval source. Replace `/path/to/completed-eval`; no source is downloaded or inferred.
Model stages use the referenced model catalog and secret environment and incur
charges. Copy this directory and adjust catalog and source paths before use.

| File | Responsibility |
|---|---|
| `runtime.example.yaml` | Model bindings and component references |
| `research-subagent.yaml` | Four concurrent workers, 32 conversations, 3600 seconds and 256 requests per worker |
| `research-evidence-selection.yaml` | Trajectory materials with explicit termination diagnostics |
| `research-context-budget.yaml` | Reduction at 65% of model input capacity, with a target of 45% |
| `research-compaction.yaml` | Layered compaction settings for the research runtime |
| `research-organizer.yaml` | Organizer settings for the research runtime |
| `research-editor.yaml` | Five bounded draft repair attempts |
| `improvement.example.yaml` | Explicit independent stages and named inputs |

Each organize/propose invocation allows 86400 seconds, 536870912 evidence
characters and 16384 evidence responses. Worker local limits remain separate:
2097152 characters and 512 responses. These are maxima, not target consumption
or monetary quotas. Keep the four-worker limit until service behavior is observed.
Ordinary installed defaults and daily model bindings need not change.

```bash
fruitfly-agent-lab improvement show --config examples/experiments/large-batch/improvement.example.yaml
fruitfly-agent-lab improvement check --config examples/experiments/large-batch/improvement.example.yaml
# Explicit model work after source paths and credentials are configured:
fruitfly-agent-lab improvement step --config examples/experiments/large-batch/improvement.example.yaml
```

Run import first. Select organize explicitly, then inspect its findings, provenance,
coverage and child failures before selecting propose. Inspect `decision.json`
before selecting execution: evidence requests and baseline retention have no new
candidate. No stage automatically starts the next stage or activates a candidate.

Investigate groups of about 8 to 12 cases. Use `catalog(kind="executions")` and
read individual summaries, then selected trajectory pages. Workers save detailed
findings blocks and finish with a compact summary. Inspect exact source spans,
counterexamples and gaps instead of treating a successful tool call as task success.

When a role fails, retain its Sessions, shared working files and organization
parts. Explicit incremental reuse validates source identities and execution
conditions. Existing recovery inspects unfinished attempts; it does not replay
models or automatically resume arbitrary candidate edits from another run.
Explicitly grant an `editor-draft-retained` artifact through stage `context`
and use `restore_candidate` to restore edits under the current baseline and
grants. Read the relevant current sources before submitting. Working files
remain attributed context rather than automatic authorization. Missing required sources remain
an explicit blocker, not an implicit baseline-retention decision.

Offline validation uses fake Providers and does not establish model quality:

```bash
.venv/bin/python -m unittest tests.workflows.test_large_batch_research tests.run.test_research_delegation tests.run.test_organization_parts tests.lab.test_editor_execution tests.lab.test_evidence_selection
```

## Run an independent grouping comparison

Add a referenced I component with ID and implementation `improvement-grouping`
to a copy of the runtime profile. The following is a component file.

```yaml
id: improvement-grouping
role: I
implementation: improvement-grouping
parameters:
  settings:
    method: random
    batch_size: 12
    seed: 19
```

After publishing a frozen batch under the alias `pool`, add the following stage
to the research document. Set `next.stage: group` and invoke
`fruitfly-agent-lab improvement step --config .fruitfly/improvement.yaml`.
Replace the alias if the imported pool was published under a different name.

```yaml
group:
  position: 0
  inputs:
    batches:
      - artifact: pool
  publish_as: random-group-0
```

Grouping runs offline. Choose another explicit position and output alias for
another group. Copy the research document or select another branch when setting
up another experimental condition. Preserve the pool, parent Harness, editor,
and allowances across the conditions being compared.

Select the group alias as the sole batch input for `organize`, then invoke that
stage independently. Supply its bundle as evidence and the same group bundle as
the batch for `propose`. Organizer and Proposer call their configured models.
The group receipt and feature table stay with the research outputs. The model
receives the selected batch, its material plan, and the granted organized view.

For a source-external test, invoke `execute` separately with the baseline and
the selected candidate against the same declared task and attempt population.
Execution can invoke models and task backends. Compare the frozen results
offline with the default measured comparison component. Native execute outputs
need no manual conversion or paired manifest.
The authoritative measurement source must provide attempt, scorer and outcome
policy identities. [Configure measured comparison](../../../fruitfly_agent/lab/improvement/assessment/README.md#compare-explicitly-paired-measurements)

The Organizer example uses two concurrent workers, at most six child executions
and 32 model requests per child. Its 30-minute invocation and shared 512000-character,
128-response reading allowance are starting controls for Flash models. Review
actual completion and evidence quality before enlarging them. Other stages keep
their own allowances. Reuse validates retained material and worker conditions.
