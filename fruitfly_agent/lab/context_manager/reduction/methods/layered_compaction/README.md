# Use layered compaction

[Up: Reduction](../../README.md)

`LayeredCompactionReducer` implements `ContextReducer`. The default
`layered-compaction` selection uses deterministic mode. It requires `read-tool`
so every abbreviated result and archive remains readable. No auxiliary Provider
is resolved in this mode.

## Follow the stages

| Stage | Trigger and behavior |
|---|---|
| Preview old results | Eligible long text tool results become head/tail previews with an original-message URI; preserve status and call/result pairing. Recent groups stay intact unless an oversized request requires previews. Image results retain their original content. |
| Archive history | At `trigger_ratio` of available input capacity, aim for `target_ratio`. Keep the first task, latest user input and recent complete groups; replace earlier history with an immutable manifest and readback instructions. |
| Summarize evidence | Hybrid mode only: one bounded request over supplied evidence. Oversized entries become explicit source references; the representation ledger distinguishes supplied text, previews and references. |
| Commit | Propose only a smaller fitting request. Core checks final measurement, pairing, replay permission, revision and cancellation before durable commit. |

Capacity subtracts system/tool input, output reserve and measurement uncertainty.
The tail target is soft: the minimum complete groups and pinned user input can
exceed it. A request that still cannot fit fails through ordinary Core preflight;
it does not silently truncate the task or invent a successful summary.

Hybrid summaries require six sections: request/constraints, work/decisions,
technical details, files/changes, errors/uncertainty, and pending work/next action.
Only nonblank normal final text with those sections in order and within the
summary text limit is accepted. Empty, truncated, invalid, oversized, timed out
or ordinary failed responses fall back to deterministic archiving. Cancellation
propagates after stream cleanup. Unconfirmed cancellation and outer model-budget
exhaustion remain fatal. A deadline includes measurement and streaming; cleanup
uses the shared bounded cancellation contract.

## Configure and improve

The strict dataclass in `config.py` owns defaults and bounds. Author component
syntax through [Catalog configuration](../../../../catalog/CONFIGURATION.md).
The [example](../../../../../../examples/configuration/README.md#select-reduction-and-measurement)
shows mode selection and field grants.

| Surface | H candidate admission |
|---|---|
| Trigger/target ratios, preview size, old-result threshold, recent-group count and tail budget | Editable in both modes |
| Readback instructions | Editable in both modes |
| Summary instructions, desired size, input/output limits and timeout | Editable only in hybrid mode |
| Mode and `models.roles.context_summary` | User configuration; protected from candidates |
| Source coverage/hash, artifact references, pairing, retry interval and outer budgets | Fixed integrity policy |

Hybrid mode requires an explicit existing alias at `models.roles.context_summary`.
It never implicitly borrows the executor. Its auxiliary output is capped by both
component policy and the model binding. Hybrid inference and optional Provider
counting can use the network and incur charges; deterministic compaction itself
makes no auxiliary model requests.

## Recover state

Each runtime owns a Session-scoped `compaction` resource mount. Source text stays
in canonical Session records. Immutable manifests/summaries live in
`SESSION.jsonl.artifacts/reduction/layered_compaction/<sha256>.txt` and are read
through [history resources](../../../resources/README.md). Trial exports use
`layered_compaction/` paths. No filesystem path is sent as a source URI.

A checkpoint binds the policy hash, source count/hash, active artifact dependencies
and last summary attempt. Recovery rejects missing/corrupt active material or a
changed canonical source prefix. Repeating the same material makes no new summary
request. Changed material requires at least eight new canonical messages under
the same policy. New policy identity resets admission; trials receive fresh
Session/artifact scopes. Run rebuilds projections when active configuration changes.
State-only failed-attempt commits do not count as compactions.

## Find implementation and checks

| File | Responsibility |
|---|---|
| `algorithm.py` | Stage ordering, capacity admission, proposals and recovery |
| `projection.py` | Pure previews, complete-group cuts, anchors and evidence representation |
| `summary.py` / `prompts.py` | One summary operation and editable text |
| `state.py` | Source identity, artifact checks and retry admission |
| `config.py` / `registration.py` | Strict policy and Catalog installation |
| `improvement.py` | Conditional owner whitelist and protected fields |
| `resources.py` | Scoped shared-history installation |

`ContextSnapshot.report_activity` reports archiving, summarizing and reducing with
safe stage/outcome labels. Session records include elapsed time and reported
auxiliary token usage without storing prompts or credentials in activity events.
The terminal shows these stages while preparing the main request.

```bash
.venv/bin/python -m unittest tests.lab.test_layered_compaction tests.lab.test_layered_compaction_failures tests.workflows.test_layered_compaction_improvement
```

Offline fake Providers establish covered execution and isolation, not factual
summary quality. Deterministic archives require later retrieval of details;
heuristic token estimates and head/tail previews do not preserve every fact in
the active projection. There is no semantic retrieval or background memory job.
