# Context Pipeline

[Up: Core](../README.md)

Execute the fixed stages `augmentation → externalization → reduction`. Lab supplies the algorithms; Core owns ordering, failure isolation, and commits.

| Contract | Input | Output / behavior |
|---|---|---|
| `ContextTransformer` | Read-only `ContextFrame` | New frame, transform with metadata, or `None`; sync or async |
| `ContextReducer` | `ContextSnapshot` | Proposed `ContextDecision`; Core validates and persists it |
| `ContextStage` | Stable stage ID and implementation | Ordered by phase, then stage order and ID |
| `ContextSnapshot.signal` | Optional run cancellation event | Observe or pass to auxiliary calls; never serialize or set it |

Frozen containers do not make nested messages deeply immutable. Reduction changes the projection, not the canonical transcript. Core checks cancellation after reduction; algorithms enforce their own auxiliary-call budgets.

| File | Responsibility |
|---|---|
| [models.py](models.py) | Frames, stages, and protocols |
| [manager.py](manager.py) | Ordering and execution |
| [../context_runtime.py](../context_runtime.py) | Reduction commit and recovery integration |

Add implementations through [Lab Context manager](../../lab/context_manager/README.md) and [Catalog](../../lab/catalog/README.md). No module-specific environment variables.

```bash
.venv/bin/python -m unittest tests.lab.test_context_pipeline tests.core.test_loop -v
```

## Commit state and measure input

[budget.py](budget.py) defines `InputMeasurement`, `ContextMeter`, request identity
and transparent Provider capability forwarding. [history.py](history.py) defines
the injected history reader; [validation.py](validation.py) checks complete tool
pairing and optional Provider rebase constraints. [tasks.py](tasks.py) bounds
external context work and cancellation cleanup. Core contains no estimator or
summary prompt.

A decision may carry JSON `state` without replacing messages. Projection and
checkpoint commit only after final hooks, pairing/replay/budget checks, stale
revision and cancellation checks, and successful synchronous persistence. A
failed write preserves both previous active values and stops the run with
`context_commit_unconfirmed`; durable outcome must be checked by reopening the
Session. No main request follows an unconfirmed commit. State-only commits use `meta`
`context_state` records; combined changes use one compaction entry. Checkpoints
are restored by mechanism identity, separately from immutable canonical messages.

`ContextSnapshot` includes measurement, checkpoint state, revision and a generic
`rebase_allowed` capability. Lab methods control policy; Core revalidates actual
final output. Preflight budget failures do not call the Provider. Heuristic
measurements retain their uncertainty and cannot guarantee remote acceptance.
