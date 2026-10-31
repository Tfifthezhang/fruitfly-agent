# Execution Definitions

[Up: Improvement](../README.md)

Select execution through registration metadata. Run consumes this public capability;
frontends receive plain views and do not import a runner implementation.

## Register an execution definition

`ExecutionRegistry.register(ExecutionDefinition(...))` registers an ID, label,
implementation identity, supported H/S/I roles, capabilities, material discovery,
preparation, construction, parameter declarations and cost notice. Discovery reads
metadata/materials without constructing Providers or starting model work.

| Entry | Responsibility |
|---|---|
| [__init__.py](__init__.py): `ExecutionRegistry` | Explicit registration and lookup; duplicate IDs fail |
| `ExecutionContext` | Borrowed task/model/component/artifact capabilities; no Application or Factory |
| [files.py](files.py) | Native file materials and optional task-package verification |
| [Experiment contracts](../../../improvement/contracts/experiments.py) | Requests, parameter declarations, prepared material and stage ports |
| [Editor experiments](../improver/README.md) | Registered fixed-depth I comparison |

Preparation validates the exact component scope, typed parameters, source hashes
and material compatibility. `PreparedExecution` keeps private material out of editor
requests. Its source query is checked again before execution. File inputs are
frozen bytes; task packages and experiment sources must still match their preview.

Construction returns `ExecutionPorts`: a runner, optional measurement/verifier/
selector, and whether pending experience may be
retained. Factories register owned resources with job services immediately.
Borrowed ports remain caller-owned. Extensions must clean up partial construction.

## Preserve existing embeddings

`WorkflowBindings.runner`, stage factories and injected verifier/measurements remain
supported. `WorkflowBindings.executions` can replace the execution registry;
`stop_policy` replaces only stop decisions. Native `file-task` remains the default.
Definitions opt in to the injected runner override with `accepts_runner_override`;
its capabilities cannot replace those of unrelated execution definitions.
An unknown execution ID, unknown parameter, incompatible component, missing scorer
fails before model work.

The default file environment supplies isolated in-memory read/write/edit files.
It does not inherit Bash, SSH, network tools, live Session or production files.
Its declaration supports H/S only. External environments require a registered
runner with truthful capabilities, state isolation and attributable receipts.
Registration is not an OS sandbox or permission to deploy code.

Native execution preserves exact Provider continuation within the Core loop. Improvement does not apply model/tool/turn count quotas. Each execution has its own time. Editor-facing trajectories omit opaque Provider state.

## Check offline

```bash
.venv/bin/python -m unittest tests.lab.test_improver tests.workflows.test_improvement_pipeline tests.architecture.test_boundaries
```

No secrets or environment variables are introduced. Real execution calls the
configured models and may incur charges.

## Record execution facts

`facts.py` attaches immutable `ExecutionFacts` to an ordinary execution receipt.
Facts bind task/material, harness, initial state, conditions, source, termination,
recorded counters, usage and collected artifacts. Missing diagnostics remain
unknown. Collection failure differs from confirmed absence; counters do not
establish task quality. Native and external runners retain their original logs.
Token facts distinguish reported subtotals from unknown totals. Composite
verifiers declare `manages_stage_times` and time each leaf execution and
measurement; ordinary verifier callbacks receive one evaluator time.
See [completed assessment](../assessment/README.md) for read-only feedback.

## Schedule task batches

`scheduler.py` owns `TaskScheduler`: a bounded queue with fixed result ordering,
cancellation and cleanup. Single-task execution uses the same queue at concurrency
one; multiple tasks at concurrency one run serially.

`batches.py` owns `BatchEvaluator` in the Improvement runtime. Each leaf builds fresh ports and independent execution/evaluation times, recording exact task/harness/state/condition identities. Confirmed reusable receipts are cached within the same frozen run and attempt; reuse does not create a new sample.

Task and source failures remain distinct from scored zero. Interrupted batches
save completed receipts and incomplete coverage. User cancellation
propagates. Completed model assessment runs on development evidence;
private selection trials do not produce editor feedback. See [Task sets](../task_sets/README.md).

## Stream evidence and control a probe

`file_runner.py` owns native execution and its public `FileTaskRunner` entry.
`control` and `aclose`. Final-only runners use `CompletionOnlyRunner` and expose no
invented intermediate measurements. `events.py` persists immutable ordered event
references for independent readers. Text streaming is not required by every backend.

`control.py` validates capability, version, evidence position and idempotency.
Current managed handles support scoped stop, not arbitrary steering, checkpoint,
fork or live component replacement. Unsupported/stale controls are rejected. A handler failure records an unknown
control outcome and the same request is not replayed.
`segments.py` defines explicit version/checkpoint/state-transfer lineage for
backends supplying those capabilities; a contract is not a filesystem or process
snapshot implementation. Stopping a probe does not cancel the root job.

[Online assessment](../assessment/README.md) consumes committed evidence without
accessing mutable Core state. In-flight changes are not installed into the same
Agent loop. A changed I is rebound at the next editor invocation/generation.

Hosted native file execution restricts its read/write/edit tools to the configured
tool set. Standalone `FileTaskRunner` callers may explicitly pass `tool_names`;
omission retains the detached runner's established three-tool default. All
declared scalar execution settings reach Core; final values are saved as
`runtime-execution.json`. Backend isolation remains active. Improvement uses independent phase times and records usage without count quotas.

## Validate declared task outputs

`deliverables.py` defines `DeliverySpec` and `DeliveryBundle` for task-produced
files. They are separate from `CandidateBundle`, which describes harness edits.
File execution accepts `delivery_manifest`, naming a frozen JSON task input. The
manifest declares an `entrypoint`, `dependencies`, allowed `inputs`, optional
`arguments`, `timeout_seconds` (1–600, default 30) and `require_stdout` (default
true). Paths must be distinct and relative; unknown or duplicate JSON keys fail.
Declared output files must come from collected execution deliverables, and inputs
must come from the frozen task. No ambient file becomes an implicit dependency.

The default in-memory runner has no command execution capability. A manifest
therefore requires an explicitly supplied `WorkflowBindings.delivery_backend`;
preparation rejects unsupported execution before model work. Task packages without
file inputs reject this parameter. [Delivery verification](../verification/README.md#validate-delivery-bundles)
owns backend behavior, results and clean-directory limits. Existing executions
without a manifest retain their declared behavior.

Native file trials apply `ComponentRegistry.trial_setups` before owner projections.
Each setup supplies a fresh Core hook registry and owned state; resources retire
at the execution boundary. Unsupported runners reject the `execution-setup`
requirement rather than silently omitting a registered mechanism.
