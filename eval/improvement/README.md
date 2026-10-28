# Benchmark Improvement Adapter

[Up: Eval](../README.md)

Register external task execution with the independent Improvement framework.
`eval run` remains a fixed-version benchmark evaluation; there is no parallel
`eval improve` entry or implicit evolution. Normal Improvement/RSI work without Eval.

| File | Responsibility |
|---|---|
| `registration.py` | Offline discovery and source/condition/capability validation |
| `building.py` | Materialize owner-declared prompt/artifact bindings into a separate configuration |
| `runner.py` | Execute with a held model allowance and attributable receipts |
| `process.py` | Invoke existing Eval CLI and use its cancellation/cleanup path |
| `evidence.py` | Collect Agent trajectories and deliverables; exclude private verifier content |
| `facts.py` | Translate terminal loop diagnostics, model allowance and artifact collection status |
| `assessment.py` | Official development rewards without independent assurance |
| `configuration.py` | Experiment request references and derived bounded host files |
| `episodes.py` | Inject prepared benchmark episodes for fixed-I comparisons |
| `task_sets.py` | Frozen benchmark collections and exact per-task execution through common task-set ports |

## Prepare and register

The standard [experiment CLI](../../fruitfly_agent/experiments/README.md) registers
this adapter from `task.source: eval`; no Python assembly script is required.
It derives the host model allowance from `task.model_calls` (default 80), preserves
the original host and uses the derived file for `eval prepare`, `check` and search.
Ordinary Eval still evaluates one fixed version.

Embedding hosts can also register explicitly. Use a request and host file in the
same improvement workspace. Prepare
current source and a Linux runtime using [Harbor preparation](../harbor/README.md).
Set host `environment.agent.FRUITFLY_MAX_MODEL_CALLS` to the declared per-execution
allowance before preparation. The bridge records main/auxiliary request counts in
`agent/model-budget.json`. Old frozen implementations are rejected before model
work. Source checks also require the configured tool-limit and execution-facts
implementation; refresh preparation after runtime changes. Limits cover harness Provider invocations, not SDK retries or arbitrary
requests made by task shell code.

This offline composition example uses placeholder paths and allowance 80:

```python
from pathlib import Path
import os
from eval.improvement import benchmark_execution
from fruitfly_agent.lab.improvement.api import builtin_executions, WorkflowBindings
from fruitfly_agent.run import RunApplicationFactory

workspace = Path('/path/to/workspace')
executions = builtin_executions()
executions.register(benchmark_execution(
    workspace / '.fruitfly/eval-request.json',
    workspace / '.fruitfly/eval-host.yaml',
    model_calls=80,
))
factory = RunApplicationFactory(cwd=workspace, environment=dict(os.environ),
    improvement_bindings=WorkflowBindings(executions=executions))
```

Start an Application with that factory and submit a `WorkflowRequest` selecting
`execution_id='benchmark-task'`, `task_pack_id='benchmark-task'`, declared H/S
components and measured feedback. Preview makes no Docker or model request.
Execution starts containers and models and may incur charges. Discovery reports
missing preparation instead of silently downloading it. The chat menu is a light
native-task entry; full experiments use the independent CLI or public API.

## Interpret scope and evidence

One task, one attempt and concurrency one are supported per leaf execution.
The [task-set adapter](../../fruitfly_agent/lab/improvement/task_sets/README.md)
can expose many such leaves from a larger prepared selection. Editor instructions remain an I-comparison responsibility: this runner
cannot establish I improvement from a direct task score. Prepared benchmark studies use the explicit [I comparison composition](#compare-i-on-prepared-benchmarks).

The request, host, preparation and source model/configuration bytes bind material
identity. Candidate configurations never overwrite the source profile. Each
execution retains its own controller log under the Improvement job; complete Eval
reports and official logs remain in `.fruitfly/eval/<id>/`. Agent trajectory and
collected deliverables enter editor evidence; verifier tests/answers do not.
Official reward is available only through declared development measurement.

`execution-facts.json` follows the common Lab contract. A single Agent Session's
terminal record supplies the recorded termination cause and attempted/started/
skipped tool counts; `model-budget.json` supplies the execution model allowance.
Collection manifests distinguish collected/empty, confirmed absence, failure and
unknown. A failed collection is not evidence that a deliverable was absent.
Legacy receipts without diagnostics remain unknown/incomplete. Facts and optional
completed-process assessments are diagnostic editor resources; private verifier
answers and logs are excluded, and official reward/assurance are unchanged.

Parent quota holds the complete per-execution allowance before launch. Confirmed
usage settles actual calls and returns unused quota. Unknown interrupted usage
conservatively consumes its held allowance; `observed_calls` remains null and the
journal distinguishes quota charged from actual calls. A separately injected
independent verifier is required for persistent publication. No benchmark reward
alone changes daily defaults or commits experience.

Online handles currently expose lifecycle progress and scoped stop; they do not
claim checkpoint, fork, state transfer or hot replacement. Original task containers
and official grading remain Harbor-owned. No source/plugin loader is introduced.

```bash
.venv/bin/python -m unittest tests.eval.test_improvement tests.eval.test_execution_facts tests.run.test_model_budget
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
task-set experiment prepares its Eval sources through derived bounded hosts;
native collections need no Eval preparation. No additional benchmark adapter or
package is installed by declaring a collection name.

## Compare I on prepared benchmarks

`benchmark_improver(development, verification, ...)` composes nonempty, disjoint
sets of prepared one-task `benchmark_execution` definitions. It returns an
execution definition for the ordinary Improvement registry. The adapter injects
material construction and `EpisodeExecutor`; Lab imports no Eval implementation.
Task execution alone does not install this comparison.

For example, after preparing separate development and verification requests and
bounded hosts, register the following with the same `executions` registry and
factory shown above. These are placeholder paths; running the resulting study
starts repeated model and container work and can incur substantial charges.

```python
from eval.improvement import benchmark_improver

executions.register(benchmark_improver(
    (benchmark_execution(workspace / 'development-request.json',
                         workspace / 'development-host.yaml',
                         model_calls=2, execution_id='development'),),
    (benchmark_execution(workspace / 'verification-request.json',
                         workspace / 'verification-host.yaml',
                         model_calls=2, execution_id='independent'),),
    max_verifications=1,
))
```

Select `execution_id='benchmark-improver'`,
`task_pack_id='benchmark-editor-study'`, I components and scored feedback in the
ordinary `WorkflowRequest`. Set `evaluation_model_calls` at least as high as every
prepared per-task allowance and fund `inner_model_calls` for both leaf executions
and editing. Preparation computes the shared minimum, including protected paired
verification for persistent jobs. Root limits remain hard comparison conditions.

Each episode freezes candidate I while the inner workflow edits H/S, then measures
before/after H/S through the benchmark's official score. Inner component capability
checks remain mandatory. Development and verification inputs must be distinct;
source changes invalidate the study. Input identity checks do not prove semantic
independence across related tasks. Verification-use claims follow the ordinary
I comparison policy. All nested model calls and executions charge the root once;
uncertain external usage remains conservatively charged. Only independently
verified I is eligible for explicit activation. Inner H/S is never activated by it.

This composition is currently exposed through the public embedding API; the
experiment file `source: editor` still selects native task-package episodes.
Offline injected executors cover nested modification, scoring, partitioning,
isolation and accounting in `tests.eval.test_improvement`.

Interrupted collection retains available original evidence even when the last
Session line or model-budget receipt was only partly written. Such counts remain
unknown and consume the held maximum; incomplete files cannot grant a score or
complete diagnostics. Completed receipts still require strict parsing.
