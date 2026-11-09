# Benchmark Improvement Adapter

[Up: Eval](../README.md)

Register external task execution with the independent Improvement framework.
`eval run` remains a fixed-version benchmark evaluation; there is no parallel
`eval improve` entry or implicit evolution. Normal Improvement/RSI work without Eval.

| File | Responsibility |
|---|---|
| `registration.py` | Offline discovery and source/condition/capability validation |
| `building.py` | Materialize owner-declared prompt/artifact bindings into a separate configuration |
| `runner.py` | Execute with independent execution time and attributable receipts |
| `process.py` | Invoke existing Eval CLI and use its cancellation/cleanup path |
| `evidence.py` | Collect Agent trajectories and deliverables; exclude private verifier content |
| `facts.py` | Translate terminal loop diagnostics, observed usage and artifact collection status |
| `assessment.py` | Official development rewards without independent assurance |
| `configuration.py` | Experiment request references and derived host files |
| `episodes.py` | Inject prepared benchmark episodes for fixed-I comparisons |
| `task_sets.py` | Frozen benchmark collections and exact per-task execution through common task-set ports |

## Prepare and register

The standard [experiment CLI](../../fruitfly_agent/experiments/README.md) registers this adapter from `task.source: eval`. It preserves original host files and stages a derived host for preparation, checking and execution. Ordinary Eval evaluates one fixed version.

Embedding hosts can register explicitly with request/host files in the workspace. Prepare current source and a Linux runtime through [Harbor](../harbor/README.md). The bridge records main/auxiliary request status and reported usage in `agent/model-usage.json`. Prepared source must match configuration, execution and evidence implementations before model work.

This offline composition example uses placeholder paths:

```python
from pathlib import Path
import os
from fruitfly_eval.improvement import benchmark_execution
from fruitfly_agent.lab.improvement.api import builtin_executions, StageBindings
from fruitfly_agent.run import RunApplicationFactory

workspace = Path('/path/to/workspace')
executions = builtin_executions()
executions.register(benchmark_execution(
    workspace / '.fruitfly/eval-request.json',
    workspace / '.fruitfly/eval-host.yaml',
))
factory = RunApplicationFactory(cwd=workspace, environment=dict(os.environ),
    improvement_bindings=StageBindings(executions=executions))
```

Start an Application with that factory and submit a `WorkflowRequest` selecting
`execution_id='benchmark-task'`, `task_pack_id='benchmark-task'`, declared H/S
components and measured feedback. Preview makes no Docker or model request.
Execution starts containers and models and may incur charges. Discovery reports
missing preparation instead of silently downloading it. The chat menu is a light
registered-task entry; full experiments use the independent CLI or public API.

## Interpret scope and evidence

One task, one attempt and concurrency one are supported per leaf execution.
The [task-set adapter](../../fruitfly_agent/lab/improvement/task_sets/README.md)
can expose many such leaves from a larger prepared selection. Editor instructions remain an I-comparison responsibility: this runner
cannot establish I improvement from a direct task score. Automatic nested I comparison is not an installed execution backend.

The request, host, preparation and source model/configuration bytes bind material
identity. Candidate configurations never overwrite the source profile. Each
execution retains its own controller log under the Improvement job; complete Eval
reports and official logs remain in `.fruitfly/eval/<id>/`. Agent trajectory and
collected deliverables enter editor evidence; verifier tests/answers do not.
Official reward is available only through declared development measurement.

`execution-facts.json` follows the common Lab contract. A single Agent Session's
terminal record supplies the recorded termination cause and attempted/started/
skipped tool counts; `model-usage.json` supplies observed requests.
Collection manifests distinguish collected/empty, confirmed absence, failure and
unknown. A failed collection is not evidence that a deliverable was absent.
Absent diagnostics remain unknown/incomplete. Facts and
completed model assessments are diagnostic editor resources; private verifier
answers and logs are excluded, and official reward/assurance are unchanged.

Known request counts contribute observations to the enclosing report; missing or interrupted usage remains unknown. There is no reservation or conservative charge. Independent verification remains required for persistent publication. Benchmark reward alone cannot activate a candidate.

Online handles currently expose lifecycle progress and scoped stop; they do not
claim checkpoint, fork, state transfer or hot replacement. Original task containers
and official grading remain Harbor-owned. No source/plugin loader is introduced.

```bash
.venv/bin/python -m unittest tests.eval.test_improvement tests.eval.test_execution_facts tests.run.test_model_usage
```

Tests use injected executors and synthetic rewards, never Docker or real models.
Actual container/model compatibility requires a separately authorized experiment.

Each candidate stages the frozen component contents and a private copy of the
model catalog, so baseline execution cannot silently use a different prompt or a
later catalog edit. Empty unchanged components retain their declared default.
Source attribution visible to editing is opaque; exact task IDs remain in Eval
receipts. No reference solution or private grader output is added to task inputs.

## Expose a prepared task collection

`task_sets.definition()` registers the `eval` collection source. It consumes the
benchmark catalog and prepared rows without knowing a particular dataset. Each
leaf request carries one exact `benchmark.task_names` entry, stages its own
candidate configuration and returns ordinary facts and official development
measurements. Lab's shared scheduler owns attempts and concurrency; leaf request
files require attempts/concurrency one.

Collections share the experiment workspace and base Agent configuration/profile.
Relative request `runtime.working_directory` paths resolve from that workspace,
including when the CLI uses `--cwd` from another process directory. Leaf requests
carry the resolved absolute workspace; paths selecting another workspace fail.
Conflicting executor overrides fail rather than silently changing conditions.
Optional `task_names`, `partitions`, `groups` and objective ranges describe the
prepared inventory. Source changes invalidate execution. `eval prepare` on a
task-set experiment prepares its Eval sources through derived hosts;
custom non-Eval sources own their preparation. No additional benchmark adapter or
package is installed by declaring a collection name.

## Register compact permitted evidence

The bridge extracts task instructions and a single reading trajectory from the
native Session, falling back to converted ATIF when native evidence is absent.
Each step contains visible text/tool calls/results with 2000-character excerpts,
original lengths, truncation markers and original source spans. Provider replay
state, thinking blocks and duplicate event streams are excluded from default input.
Usage receipts, process status, final answer and execution facts remain separate.
Failed trials without a Session remain discoverable through explicit gaps and
startup observation summaries.

`materials.py` owns Eval layout adaptation. `diagnostics/reading-scope.json` lists
permitted source paths, hashes, sizes, external/retained/invalid states and parse
gaps. Captured files are indexed without copying their bodies by default. Explicit
`stages.import.evidence_paths` supplements freeze selected files after hash checks.
Original trajectories supplied this way are diagnostic sources, not extra runs.
See [import settings](../../fruitfly_agent/experiments/CONFIGURATION.md#select-imported-evidence).

`diagnostics/final-answer.json` records whether the last retained assistant answer
is final, partial or absent, together with its original source span. The execution
output uses the actual answer rather than a generic runner sentence. The complete extracted answer is available in the final-answer resource;
original Session pages require an explicit supplement.
Usage extraction is independent of ATIF conversion and retains known subtotals
when full totals are unknown.

The shared organizer supplies overview, events, coverage and source navigation.
`ExecutionFacts.complete` still describes execution diagnostics; it does not claim
complete file collection. Both ordinary Eval post-processing and Improvement use
the same [evidence implementation](../../fruitfly_agent/lab/improvement/evidence/README.md).
Neither an organized directory nor a human analysis report bypasses resource grants.

## Import retained execution evidence

`history.import_history(run, artifacts)` converts permitted retained Harbor task
evidence into a benchmark-neutral `ResearchBatch`. It preserves available task
instructions, separate execution status and official reward observations, immutable
reading materials, original source locators and diagnostic provenance. Verifier answers remain excluded. Missing
instructions are explicitly marked; previous harness, source and initial learning
state are not reconstructed. Import supports diagnosis and proposal, without a
fresh baseline or an assumption of comparable execution conditions.

Historical imports accept an associated report directory through `related_records`.
Available configuration declarations and runtime receipts are retained as separate
provenance resources. Missing original source or learning-state reconstruction
remains explicit. The associated report is not a second independent execution
batch and its conclusions do not replace original trajectories.

Default import and new Eval executions use the same compact collector. They need
no model organizer before assess/propose. Portable exports retain their registered
materials, while unselected original bytes remain external dependencies. Historical
batches are immutable; explicitly reimport to create a compact batch or supplement.
Offline checks include `tests.eval.test_reading_materials` and
`tests.workflows.test_improvement_evidence`.
