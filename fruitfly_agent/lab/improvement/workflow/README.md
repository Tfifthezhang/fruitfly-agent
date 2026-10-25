# Workflow and Execution

[Up: Improvement](../README.md)

[__init__.py](__init__.py) exports the default `WorkflowController`,
`GeneratorRegistry`, shared allocation and cancellation services. Generation,
composition, execution, selection, optional verification and reflection use
public ports. No stage activates a candidate.

Parallel proposals share frozen references and prior history. Sequential rounds
carry the declared exploration seed and accumulated execution evidence; the default
seed is the official incumbent. Scope, ownership, evidence
citations and task/state/condition receipts are checked before reuse. Generator
factories create job-local state; discovery uses registration metadata only.

[execution.py](execution.py) exports the execution module's `FileTaskRunner`: fresh in-memory files,
read/write/edit tools, exact owner projections, root-budgeted model calls and
immutable output/trajectory resources. It uses final-stage answers. Bash, live
network tools and ambient Session/filesystem access are absent. Other runners
must declare capabilities and return attributable receipts.

Services reserve calls before work and cancel outstanding tasks on timeout or
cancellation. Exhaustion never invents a complete or verified result. No in-flight
work is replayed after process loss. Independent verification consumes the same
root allocation. Token and monetary limits require additional host accounting.

Offline checks: `tests.lab.test_improvement_pipeline`,
`tests.lab.test_retained_targets`, `tests.workflows.test_improvement_pipeline`.

Per-job factory products can implement `JobResource.aclose`. The Run host registers
ownership immediately, deduplicates objects and closes in reverse order after
success, failure or cancellation. Cleanup waits at most ten seconds per resource
(or the smaller operation timeout) and records failures. Borrowed verifier and
measurement ports remain caller-owned. Embeddings use `async with WorkflowServices`
or close their services explicitly after execution; generator factories must clean
up partially failed construction.

## Retain results and stop explicitly

Every successful reference, probe and composition remains selectable. The original
reference is retained before exploration. Measured ties or missing measurements
keep the official incumbent; unscored output choice has no independent assurance.
The independent exploration policy can choose another completed harness for the
next proposal, with attributed reasons. It cannot change the reported selection.

[stopping.py](stopping.py) supplies pure `SearchState`, `StopPolicy` and
`BoundedStopPolicy`. Round limits, no candidate, repeated candidates and generator
stop are recorded separately from quality assurance. These rules are bounded
search decisions, not a convergence proof. The host can inject another stop
policy through `WorkflowBindings`.

[budget.py](budget.py) supplies `BudgetScope`. Child quota is held rather than
spent; leaf reservations charge every ancestor once. Closing returns only unused
quota. Deadline and cancellation inherit through nested operations. Final
selection holds up to eight model requests when available; independent verification
has its own protected allocation. Exhaustion retains an already completed result
without granting verification. Composite runners set `execution_charge=0` and
charge their leaf executions; trial count is independently bounded.

## Responsibility boundaries

`controller.py` owns the compatible single-task entry and validation; registered
[strategies](../strategies/README.md) supply references, missions, rounds and optional
composition counts. The controller contains no fixed invariant/domain pairing.
`services.py` owns job operations and
resources. Concrete file execution is in `execution/file_runner.py` under the
[execution module](../execution/README.md); the old import forwards explicitly.
Generator registration belongs to the editor. Pure stop implementations belong
to [Termination](../termination/README.md), and read-only selection belongs to
[Assessment](../assessment/README.md). `adaptive.py` translates declared online
conditions into control requests rather than implementing another Agent loop.

Selection runs at completed rounds and retains earlier results on measured ties.
`SearchState` includes phase, no-gain/failure counts, final completed-process
assessments, usage and assurance. Structured stop
decisions are journaled. Protected final-selection quota is released before the
last selection. External child budgets can settle already held work after
cancellation; uncertain actual usage remains explicitly distinct from quota charged.

With an explicit artifact port, the controller validates or attaches execution
facts before supplying read-only completed assessment. Run supplies this port;
existing standalone embeddings without artifact storage retain their original
receipt behavior. Official measurement and selection do not use process scores.
Assessment/exploration implementations belong to their registries, not task- or
benchmark-specific controller branches. Required unavailable assessment ends
search before independent publication.

## Share one search loop

`engine.py` owns `SearchEngine`: round missions, sequential candidate probes,
optional composition, selection, stopping and next-seed transitions. `problems.py`
defines its explicit operation callbacks. Single tasks and task sets use this same
engine and [execution queue](../execution/README.md#schedule-task-batches).

`task_sets.py` supplies batch operations. It compares the current seed and challenger
on identical sampled tasks, then promotes through a full common selection set.
Its source, sampling, evaluator, aggregation and comparison dependencies remain
replaceable. Formal selection, development exploration and independent assurance
have distinct records. See [joint search](../task_sets/README.md).
