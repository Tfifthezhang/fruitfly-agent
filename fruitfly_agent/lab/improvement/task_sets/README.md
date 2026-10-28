# Joint Task-Set Search

[Up: Improvement](../README.md)

Search one shared candidate across frozen task collections. Sources, execution,
sampling, objective aggregation and editing remain separate. No benchmark,
container or host implementation is imported here. A one-task collection uses the
same queue and search engine; concurrency one also supports a serial multi-task run.

## Run a task set

Use `task.source: task-set` in the [experiment configuration](../../../experiments/README.md).
The [annotated template](../../../../examples/experiments/multi-task.example.yaml)
combines optional Eval collections and native task packs. Paths and IDs are
placeholders. `improvement check` reads material and validates declarations without
constructing Providers. `improvement run` starts models and may incur charges.
For Eval collections, explicitly run `eval prepare` first; it can download/build
and start preparation containers. Native collections require no Eval installation.

| Entry | Responsibility |
|---|---|
| [registry.py](registry.py) | Versioned `TaskSetSourceDefinition` factories |
| [files.py](files.py) | Existing task packs; preserve train/selection/holdout |
| [sampling.py](sampling.py) | All, fixed and deterministic collection-stratified cycles |
| [configuration.py](configuration.py) | Independent typed sampling, parallel, joint and promotion settings |
| [execution.py](execution.py) | Public execution definition, frozen preview and shared `task_set_minimum_budget` calculation |
| [Contracts](../../../improvement/contracts/README.md) | Task entries, snapshots, batch receipts and editing requests |
| [Execution](../execution/README.md#schedule-task-batches) | One bounded queue and leaf allocations |
| [Assessment](../assessment/README.md#compare-task-sets) | Declared utilities, promotion and process-guided exploration |
| [Workflow](../workflow/README.md#share-one-search-loop) | One shared round engine |

## Freeze tasks and conditions

`TaskSetSnapshot` binds task namespaces, canonical origins, source/material
identities, partitions, objective ranges, and per-task model/leaf-execution limits.
Duplicate origins and cross-partition groups fail. Existing source partitions are
preserved. Editing receives only development entries, never private acceptance,
selection/confirmation inputs or verifier files. No automatic conversation mining
or synthetic summary is performed.

Every collection must expose a task objective to participate in joint ranking.
Native file collections currently select installed task packs, not ungraded
instructions. Another material format supplies a source and scorer through the
public ports. Task-set CLI search currently uses `simple`, task scope, no retained
experience, and one candidate per round. Other component kinds and I experiments
need compatible declared runners; collection registration does not bypass their
capability checks.

## Compare batches and promote

Each round evaluates the current exploration seed and its challenger on the same
task keys, attempts and conditions. The next seed defaults to the better complete
result on that shared development batch; ties retain its incumbent. Optional
`process-guided` exploration can choose another complete evaluation without changing
the formal winner. Search scores from different batches are not directly ranked.

Formal selection runs every `promotion.every_rounds` and at search completion,
using the complete common selection set. For each collection, explicit selection
entries are used when present; otherwise all its development entries are used.
Thus a pack's private validation cannot accidentally exclude another benchmark.
The previous formal harness survives incomplete or worse comparisons. Reports
distinguish official evaluation, exploration seed, collection utilities and coverage.
`selected` is development assurance, not independent verification or adoption.

Final comparison holds a separate root allocation. An unaffordable intermediate
promotion is deferred. No-gain patience advances only after a complete comparable
promotion. A repeated harness on a different sampled batch does not itself stop
search. `score` stopping can use `joint-development-v1` with `assurance: selected`.
Leaf process metrics do not implicitly become whole-task-set stop conditions.

Confirmation material stays private and unused by this development search.
Task-set persistent scope/RSI are rejected until an independent adoption policy is
registered. Search all known tasks only establishes performance on that development
set; unseen-task quality needs independent evidence.

## Extend a source

Register `TaskSetSourceDefinition(source_id, implementation_id, freeze)` in
`TaskSetSourceRegistry`. `freeze(specification, context)` returns a
`CollectionBinding`: immutable public entries, current-source query, capabilities,
roles and a private `build(leaf_context)` callback. Preparation has no model side
effects. The callback returns ordinary `ExecutionPorts`; the runner keeps the
established `TaskRunner.execute(plan, task, harness)` signature.

Each leaf gets fresh job services and its own child quota. Own resources before
fallible construction; borrowed ports remain caller-owned. Missing outcome/cost
receipts remain unknown. Composite runners declare their leaf charge and task
execution allowance. Trusted extensions are not an OS sandbox.

The experiment composition root registers built-in `files` and optional `eval`
sources. Adding another backend or task family does not add branches to Core,
Run, the scheduler or joint comparison. Models, host permissions and benchmark
grading retain their original owners.

## Inspect records

Hosted jobs save material under `materials/task-set.json`, declared `batches/`,
individual `executions/`, `evaluations/` and `comparisons/`, alongside the existing
plan, result and journal. Immutable evidence remains in `.fruitfly/artifacts/`;
complete Eval logs remain in `.fruitfly/eval/<id>/`. References connect the records.
Interrupted batches retain completed receipts and explicitly incomplete coverage.
No unknown paid work is automatically replayed.

```bash
.venv/bin/python -m unittest tests.lab.test_task_sets tests.lab.test_batch_scheduler tests.lab.test_joint_assessment tests.lab.test_task_set_search tests.experiments.test_multi_task
```

Fake rewards validate orchestration, coverage, isolation and accounting only.
Real container compatibility and quality gains require an authorized experiment.
