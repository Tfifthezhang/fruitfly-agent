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
| `research-evidence-selection.yaml` | All-policy detail grants, up to 256 cases |
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
