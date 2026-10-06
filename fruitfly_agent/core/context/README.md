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
