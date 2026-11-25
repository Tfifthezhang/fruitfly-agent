# Execute frozen task collections

[Up: Improvement](../README.md)

Freeze task collections and execute an explicitly selected harness through a
bounded leaf scheduler. Source discovery, material identity, execution and
assessment remain separate. This module installs no automatic search, periodic
promotion, Organizer invocation or production adoption loop.

## Prepare and execute a collection

The [experiment examples](../../../../examples/experiments/README.md) show prepared
Eval collections. Other sources need explicit registration. Preparation may
use downloads and containers; execution can consume model allowance and incur
charges. The ordinary task backend remains responsible for environment isolation.

Use the [independent stage guide](../DEVELOPER_GUIDE.md) to select baseline or
candidate configuration, execute it, then explicitly select retained batches for
organization, proposal or comparison. Each invocation runs one stage. An Organizer
is optional, and no missing stage is run automatically.

| Entry | Responsibility |
|---|---|
| [registry.py](registry.py) | `TaskSetSourceDefinition` and source factories |
| [configuration.py](configuration.py) | Typed sampling, execution, aggregation and promotion setting records |
| [sampling.py](sampling.py) | Explicit all/fixed/stratified-cycle sampling helper |
| [execution.py](execution.py) | Frozen preview and registered batch execution |
| [Execution runtime](../../../improvement/execution/README.md) | Bounded scheduling and leaf facts |
| [Assessment](../assessment/README.md) | Explicit model or attributed measurement comparison |

Choose exact prepared `task_names` in the Eval collection before freezing to run
a small batch. See the [small-batch recipe](../../../../examples/experiments/small-batch/README.md).
Each native batch retains its planned attempts and attributed observations for
[direct measured comparison](../assessment/methods/measured/README.md).

The registered `execute_batch` path executes the frozen development entries with
configured attempts and concurrency. The existence of sampling and promotion
settings does not schedule sampling rounds or periodic selection. Hosts using
those helpers must invoke and record the intended policy themselves.

## Freeze tasks and preserve scope

`TaskSetSnapshot` binds namespaces, canonical origins, material identities,
partitions and declared objectives. Duplicate origins and cross-partition groups
fail. Public task material stays separate from private verification data.
A registered source supplies current-source checks and leaf construction through
`CollectionBinding`. Source changes after preview reject execution.

Each leaf uses ordinary `ExecutionPorts` and fresh services with independent
phase clocks. Own resources before fallible construction; borrowed ports remain
caller-owned. Interrupted batches retain completed receipts and incomplete
coverage. Missing measurements stay unknown and do not establish task failure.

Task-set execution currently admits task scope and supported H/S component
capabilities. Persistent scope requires a separately implemented verification and
adoption policy; no automatic nested I comparison backend is installed here.
Executing all development tasks does not prove unseen-task quality.

## Extend a source

Register `TaskSetSourceDefinition(source_id, implementation_id, freeze)` in
`TaskSetSourceRegistry`. Freezing supplies immutable entries, source identity,
capabilities and a private `build(leaf_context)` callback. The callback constructs
ordinary execution ports; it does not change Core's Agent loop.
The experiment composition root supplies the optional Eval source.

The host publishes portable stage bundles and execution receipts. See
[research storage](../../../run/storage/README.md) for actual output ownership
and [Eval](../../../../fruitfly_eval/README.md) for complete benchmark logs.

```bash
.venv/bin/python -m unittest tests.lab.test_task_sets tests.improvement.test_scheduler tests.lab.test_joint_assessment tests.experiments.test_multi_task
```

Offline fixtures establish identities, scheduling and isolation, not model gains.
