# Improvement Contracts

[Up: Improvement Runtime](../README.md)

[Pipeline](pipeline.py) defines immutable task materials, component file sets,
candidate bundles, execution records, optional measurements, plans, stage requests,
selection decisions and attributed experience. Stage protocols are exported through
[the public API](../api.py). There are no model requests or filesystem operations.

| Contract | Invariant |
|---|---|
| `TaskMaterial` / `Resource` | Owned relative paths and immutable byte references; no answers |
| `HarnessSnapshot` / `ComponentDocument` | Distinct stable IDs, declared kind, axis and schema |
| `CandidateBundle` | Frozen parent, complete component set and per-edit evidence |
| `ExecutionRecord` | Task, material, harness, initial state and conditions identities |
| `SelectionDecision` | Existing run ID; output selection differs from verification |
| `JobServices` / `JobResource` | Shared budgets, cancellation, operations and optional asynchronous cleanup |
| `RunPlan` | Exact component scope, generator, modes and shared allocations |
| `ExperienceEntry` | Task attribution, lesson, limitations, evidence and reusable snapshot |

[Versions](versions.py) bind H/I/S separately. [Candidates](candidates.py) declare
actual target changes; scope checks reject undeclared axes. Concrete adapters
belong to the object owner. Role metadata does not supply execution or activation.
Run uses the same version contracts for persistent publication and recovery.

```bash
.venv/bin/python -m unittest tests.lab.test_improvement_pipeline tests.lab.test_experiment_contracts tests.contracts.test_signatures
```

## Freeze experiments and execution capabilities

[experiments.py](experiments.py) defines `ExperimentSpec`, `EpisodeRequest`,
`EpisodeResult`, `EpisodeExecutor` and `TrialReport`. Experiment identity binds
source, initial harness/state and conditions. Reports retain per-case gains,
failures, exact episode/evidence identities and actual usage. Private scorer data
is not part of `ProposalRequest` or `CompositionRequest`.

`ExecutionDefinition`, `ExecutionRequest`, `PreparedExecution` and `ExecutionPorts`
separate discovery, validation and construction. Typed parameter declarations
reject unknown or duplicate fields. Run converts these public values to frontend
views rather than exposing Lab implementations to Interactive.

`CompositionRequest.feedback` supplies explicitly permitted development
measurements. `ImprovementOutcome.verification` optionally references a completed
independent proof envelope; old outcomes without that field remain ordinary
historical data and do not acquire fabricated proof. Existing generator/composer/
runner call signatures remain unchanged. Job plan schema 2 records execution
identity and normalized request; schema 1 journals and historical reports remain
readable. A preview is never restored as authorization to rerun unknown work.

See [execution](../../lab/improvement/execution/README.md), [editor experiments](../../lab/improvement/improver/README.md)
and [budget/stop behavior](../../lab/improvement/workflow/README.md).

## Import contracts by responsibility

| File | Values |
|---|---|
| `components.py` | Documents, snapshots, publication/build/runtime/activation seams |
| `tasks.py` | Materials, resources and private acceptance-case values |
| `execution.py` | Final execution records and established TaskRunner signature |
| `facts.py` | Immutable facts, budget scope and artifact collection status |
| `search.py` | Attributed exploration decisions |
| `task_sets.py` | Frozen collection identities, task objectives and private source construction ports |
| `evaluation.py` | Expected batches, leaf trials, candidate evaluations and joint selection outcomes |
| `live.py` | Immutable event positions, assessments, metrics and controls |
| `editing.py` | Proposal/composition requests and bounded editing services |
| `assessment.py` | Measurements, selection and verification ports |
| `plans.py` | Plans and attributed experience |
| `stopping.py` | Shared cycle state and structured decisions |
| `lifecycle.py` | Frozen lifecycle events and bounded input-context contributions |

`pipeline.py` retains explicit compatible exports and orchestration outcomes.
There are no parallel definitions or implicit dynamic imports. Live payloads are
canonical JSON snapshots; readers cannot mutate committed evidence. Online
assessment status describes scope/completeness, not independent verification.

`PreparedExecution.task` explicitly accepts `TaskMaterial` or `TaskSetSnapshot`.
`ExecutionPorts.search_problem` supplies operations for the shared engine, and
`ExecutionDefinition.plan_factory` owns mode-specific bounded plans. Ordinary
`RunPlan` limits remain compatible; `TaskSetRunPlan` permits larger explicit finite
totals and binds task-set settings into comparison conditions. Batch outcomes keep
candidate evaluation IDs instead of fabricating single task executions.

`TaskSetProposalRequest` grants only development tasks and their evidence.
`TaskSetCandidateGenerator` describes that request; generator metadata declares
`supports_task_sets`. Existing single-task generator and runner signatures remain.

`ComponentBinding` and target bindings support the declared `configuration` kind.
Only supported section keys have executable adapters. `RunPlan.component_options`
freezes component field permissions and bounds; unknown or out-of-scope options
fail. `ExecutionDefinition.capabilities_for(tool_names)` derives configured tool
capabilities when `uses_configured_tools` is declared. Other backend capabilities
remain explicitly owned by the backend.
