# Improvement Contracts

[Up: Improvement Runtime](../README.md)

[Pipeline](pipeline.py) defines immutable task materials, component file sets,
candidate bundles, execution records, optional measurements, plans, stage requests,
selection decisions and attributed experience. Stage protocols are exported through
[the public API](../api.py). There are no model requests or workspace writes; default constructors may read declared package data.

| Contract | Invariant |
|---|---|
| `TaskMaterial` / `Resource` | Owned relative paths and immutable byte references; no answers |
| `HarnessSnapshot` / `ComponentDocument` | Distinct stable IDs, declared kind, axis and schema |
| `CandidateBundle` | Frozen parent, complete component set and per-edit evidence |
| `ExecutionRecord` | Task, material, harness, initial state and conditions identities |
| [`EvidenceSelector`](investigation.py) | Research case/material selection over summaries; no execution or activation authority |
| `SelectionDecision` | Existing run ID; output selection differs from verification |
| `JobServices` / `JobResource` | Observed usage, cancellation, operations and optional asynchronous cleanup |
| `RunPlan` | Exact component scope, generator, rounds and independent phase times |
| `ExperienceEntry` | Task attribution, lesson, limitations, evidence and reusable snapshot |

[Versions](versions.py) bind H/I/S separately. [Candidates](candidates.py) declare
actual target changes; scope checks reject undeclared axes. Concrete adapters
belong to the object owner. Role metadata does not supply execution or activation.
Run uses the same version contracts for persistent publication and recovery.

```bash
.venv/bin/python -m unittest tests.lab.test_detached_editor tests.lab.test_experiment_contracts tests.contracts.test_signatures
```

## Freeze experiments and execution capabilities

[experiments.py](experiments.py) defines `ExperimentSpec`, `EpisodeRequest`,
`EpisodeResult`, `EpisodeExecutor` and `TrialReport`. Experiment identity binds
source, initial harness/state and conditions. Reports retain per-case gains,
failures, exact episode/evidence identities and actual usage. Private scorer data
is not part of `ProposalRequest`.

`ExecutionDefinition`, `ExecutionRequest`, `PreparedExecution` and `ExecutionPorts`
separate discovery, validation and construction. Typed parameter declarations
reject unknown or duplicate fields. Run converts these public values to frontend
views rather than exposing Lab implementations to Interactive.

`ProposalRequest.feedback` supplies permitted development measurements. `ImprovementOutcome.verification` references independent proof when available. Job plan schema 2 records execution identity and normalized request. A preview never authorizes replay of uncertain work.

See [execution](../../lab/improvement/execution/README.md), [Independent stages](../../lab/improvement/DEVELOPER_GUIDE.md)
and [Independent stages](../../lab/improvement/DEVELOPER_GUIDE.md).

## Import contracts by responsibility

| File | Values |
|---|---|
| `components.py` | Documents, snapshots, publication/build/runtime/activation seams |
| `tasks.py` | Materials, resources and private acceptance-case values |
| `execution.py` | Final execution records and established TaskRunner signature |
| `facts.py` | Immutable facts, usage scope and artifact collection status |
| `task_sets.py` | Frozen collection identities, task objectives and private source construction ports |
| `evaluation.py` | Expected batches, leaf trials, candidate evaluations and joint selection outcomes |
| `live.py` | Immutable event positions, assessments, metrics and controls |
| `editing.py` | Proposal requests and bounded editing services |
| `assessment.py` | Measurements, selection and verification ports |
| `plans.py` | Plans and attributed experience |
| `stopping.py` | Shared cycle state and structured decisions |
| `lifecycle.py` | Frozen lifecycle events and bounded input-context contributions |

`pipeline.py` owns orchestration outcomes and the workflow protocol. Import other
values from their responsible contract modules or the reviewed runtime API.
There are no parallel definitions or implicit dynamic imports. Live payloads are
canonical JSON snapshots; readers cannot mutate committed evidence. Online
assessment status describes scope/completeness, not independent verification.

`PreparedExecution.task` accepts `TaskMaterial` or `TaskSetSnapshot`. `ExecutionPorts.search_problem` supplies operations for the shared engine. `ExecutionDefinition.plan_factory` selects the appropriate plan; both plans use `StageTimeouts`. Batch outcomes keep candidate evaluation IDs instead of fabricating single-task executions.

`TaskSetProposalRequest` grants only development tasks and their evidence.
`TaskSetCandidateGenerator` describes that request; generator metadata declares
`supports_task_sets`. Existing single-task generator and runner signatures remain.

`ComponentBinding` and target bindings support the declared `configuration` kind.
Only supported section keys have executable adapters. `RunPlan.component_options`
freezes component field permissions and bounds; unknown or out-of-scope options
fail. `ExecutionDefinition.capabilities_for(tool_names)` derives configured tool
capabilities when `uses_configured_tools` is declared. Other backend capabilities
remain explicitly owned by the backend.

## Declare optimization surfaces

`optimization.py` defines `OptimizationSpec` and `OptimizationAdapter`. Each
component adapter declares H/S/I ownership, representation, legal operations,
update timing, activation boundary, state semantics and required capabilities.
`default_selected` declares automatic selection preference, independently of
availability and explicit grants. Tool parameters default to opt-in.
Numeric configuration, text and retained documents share admission and candidate
validation. Search algorithms remain independent of target representation.
`ComponentRegistry.admit` intersects these declarations with execution support;
unsupported online updates fail before trials. Current standard runners support
offline, task-boundary candidates. Online observation does not imply online
replacement or persistent learning. Mutable fields, protected values and numeric
grants continue through owner validators; metadata grants no editing permission.

`TrialSetup` supplies fresh Core hooks and asynchronous retirement. A component
registry's `trial_setups` factories create execution-local mechanisms using the
injected job services. Supporting runners declare `execution-setup`, own each setup
before use and retire it after every trial. This contract recreates developer
extensions without borrowing live callbacks or Session state.

Text projection values `TargetBinding` and `TargetSnapshot` are defined beside
`OptimizationSpec` in `optimization.py`. `TextProjection.snapshot` returns the
concrete immutable value. Projection values identify a text view; component
ownership and candidate identity remain with `ComponentDocument` and
`HarnessSnapshot`. Owners must declare semantics rather than relying on adapter
fallbacks. A supported isolated candidate must change real execution.

Optimization adapters expose `describe_fields()` returning `OptimizationField`
values with public parameter paths, meaning, type, current/default values, unit,
bounds, choices and owner constraints. Descriptions are read-only evidence; edit
grants and owner validators remain authoritative. Hosted plans bind the metadata
identity through `component_description_id`.

Research contracts are separate from search outcomes: `activities.py` declares
activity inputs, dependencies and retained outputs; `research.py` declares immutable
configuration revisions and serializable batches; `organization.py` declares
readability requests and views. Measurements remain optional observations.

`bundles.py` declares portable typed research output manifests and producer/config
links. `configuration.py` reports field additions, removals and changes without
turning them into continuation admission decisions. The host owns path resolution
and immutable dependency copying.

`organization.py` also defines `OrganizationPart`: one attributed child finding
with its exact source grant, citation spans, producer and reuse conditions. It is
a historical evidence record, not a final guide or execution authorization.

## Set shared stage defaults

[defaults.yaml](defaults.yaml) owns independent editor, execution, evaluator and
organizer invocation times. `StageTimeouts` reads these values through Core's shared
resource decoder and validates finite positive seconds. Stage-specific research
allowances override individual times; there is no second copy in experiment
normalization. The effective values enter plan identity and configuration snapshots.
This infrastructure is protected, not a selectable algorithm or candidate surface.
The resource is build-declared and included in frozen source material.

Constructor defaults read installed package data; constructing contracts still makes
no model request or workspace mutation. Runtime does not import Lab or host loaders.

Candidate `EditReason.issue_ids` attribute changes to supplied investigation
findings when present. They supplement original execution `evidence_ids` and
testable `expected_effect`; derived findings do not replace original-reading proof.
