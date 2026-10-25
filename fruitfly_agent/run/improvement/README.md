# Improvement Host

[Up: Run](../README.md)

Bind the public Lab workflow to durable storage and Application lifecycle. Leaf
services receive explicit callbacks and stores, never the composition Factory.

| Entry | Responsibility |
|---|---|
| [pipeline.py](pipeline.py): `RunComponentJobs` | Freeze previews; assemble injected stage ports; persist outcomes and journals |
| [versions.py](versions.py): `RunVersions` | Source-backed H, declared I and registered S identity |
| [candidates.py](candidates.py): `RunCandidates` | Review, scope validation, adoption and recovery |
| [evolution.py](evolution.py): `RunEvolutionHost` | Durable RSI phases with independent verification |
| [startup_versions.py](startup_versions.py) | Explicit temporary or remembered version choices |
| [results.py](results.py) | Public material/result projections for single tasks and task sets |

Preview freezes the instruction, byte resources, components, parent H/I/S,
experience and comparison materials. Its one-use token binds exact guidance and
allocations. Changed conditions reject execution. Construction, timeout,
cancellation and ordinary failure close journal resources; submitted intent remains
in history even without a candidate.

Native file tasks use detached in-memory inputs. Full runtime, SSH or container
execution requires an explicitly injected runner through the public stage ports.
The interactive host does not discover benchmark tasks or launch Eval processes.

Persistent publication requires `verified` assurance from the injected verifier.
Changed text bindings form one version candidate, including mixed H/S changes.
Review and activation use existing host guards. Model, permissions and source
conditions are rechecked before adoption. Registration alone cannot activate code.

The public Run evolution wrapper requires an explicit workflow `request` and an
independent verifier or an exact completed proof from the registered execution. It previews each persistent proposal before invoking the
normal Application job. Unknown proposing/verifying work is not replayed; partial
activation is reconciled. One coordinator owns a job; no cross-process transaction
is provided.

See [Lab Improvement](../../lab/improvement/README.md),
[RSI](../../lab/rsi/README.md), [Storage](../storage/README.md) and
[Application adapters](../adapters/README.md). There are no new secret variables.

```bash
.venv/bin/python -m unittest tests.run.test_host_services tests.workflows.test_improvement_pipeline tests.workflows.test_evolution
```

## Bind registered execution without algorithm dispatch

`RunComponentJobs` consumes the public `ExecutionRegistry`. Lab definitions own
material discovery, validation, stage construction and acceptance. Run supplies
borrowed model/task/component/artifact ports and persists schema 2 job plans.
It does not import a concrete editor-comparison implementation. Interactive gets
execution/material/parameter views, never Lab objects.

A job records normalized execution parameters, source identity, initial H/I/S,
parent-child episode events, exact artifacts, stopping reason and assurance.
Private material remains inside the prepared execution. Model requests start only
after the one-use preview is revalidated. Protected verification quota is reserved
before search. Root reports count actual model calls and leaf task executions.

## Reuse a completed independent proof

Built-in file and editor verification produce immutable proof artifacts. The host
binds the proof to execution/implementation, normalized request, source, plan,
parent H/I/S and candidate snapshot. Candidate records reference that envelope.
`verified_candidate(record, policy_id)` revalidates scope, active parent, source,
implementation and exact candidate content, then returns `VerificationEvidence`
without rerunning models. Missing, mismatched or corrupted proof is rejected.
Custom verification remains available through an explicitly injected callback.

`run.evolution.RunEvolutionHost(..., request=request, policy_id=..., verify=None)`
uses this completed-proof path. It does not turn a development score or a human
selection into proof. Private-suite claims are durable and are not replayed after
uncertain work. See [editor experiments](../../lab/improvement/improver/README.md).

Experience review is an independent capability. Task-local lessons are staged;
Application guards explicit commit/reject while idle. Storage owns pending records
and use ledgers, while quality decisions remain in Lab.

## Keep assessment and allocations separate

Registered task-set preparation supplies a search problem through public execution
ports. Run persists typed material and batch/trial/evaluation/comparison records,
then projects candidate IDs, utilities and coverage through `results.py`. It adds
no dataset-specific dispatch or quality logic. Existing retention follows these
nested JSON records and artifact references.

Run constructs an independent read-only inspector for selection/reflection.
`WorkflowBindings.inspector` can supply another configuration/implementation;
assessors never acquire candidate write tools. Native execution parameters can
request online process assessment without changing the editor.

`WorkflowBindings.process_assessment`, `completed_assessors`, `exploration` and
`explorations` independently supply completed-assessment settings/registry and
next-seed settings/registry. Defaults disable process judgments and follow the
official incumbent. Previews freeze settings and implementation identities; changed
configuration rejects stale work. Run supplies the artifact port and separately
configured assessor, owns factory products through job services and persists their
results. It does not interpret process metrics or benchmark failures.

Reports identify the official execution separately from the exploration seed.
Only ordinary selection plus independent verification can support persistent
publication. See [completed assessment](../../lab/improvement/assessment/README.md)
and [exploration](../../lab/improvement/strategies/README.md#choose-the-next-editing-seed).

`RunComponentJobs.budget_scope` and Factory `improvement_budget_scope` borrow a
root allocation for explicitly coordinated evolution. Scopes cannot overlap;
child jobs retain their own records and charge the common root. No concrete
benchmark imports or new lifecycle authority are introduced.

Configuration candidates use the shared declarative binding adapter. Their
normalized execution values change H identity and are applied to an isolated
profile before activation. I and S remain unchanged unless separately declared
components change. [Execution policy](../../lab/execution_policy/README.md) documents
field permissions, mechanism ownership and offline activation tests.
