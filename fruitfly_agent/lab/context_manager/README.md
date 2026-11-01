# Context Manager

[Up: Lab](../README.md)

Build the model's request context through three Core stages. Canonical Session messages remain intact.

| Stage | Purpose | Implementation |
|---|---|---|
| [Augmentation](augmentation/README.md) | Add bounded instructions or retrieved information | Skills and Information spaces |
| [Externalization](externalization/README.md) | Replace large content with retrievable references | Programmatic context |
| [Reduction](reduction/README.md) | Fit the projection to the request budget | Incremental working memory |

```text
canonical messages → augmentation → externalization → reduction → model projection
```

[Measurement](measurement/README.md) is shared infrastructure used by those stages.
It is neither a context stage nor a selectable/optimizable mechanism.

## Extend a stage

| Concern | Contract |
|---|---|
| Augmentation / externalization | Implement `ContextTransformer`. |
| Reduction | Implement `ContextReducer`; Core commits valid decisions. |
| Inputs | Treat frames, snapshots, and nested messages as read-only. |
| Order | Fixed phases; `(order, stage_id)` within each phase. |
| No-op / failure | `None` preserves input; ordinary transformer errors are isolated; cancellation propagates. |
| Repeated requests | Avoid accumulating injected blocks or duplicate references. |
| State | Declare scope, reset, persistence, and recovery behavior. |

Use [Core contracts](../../core/context/README.md) and [Catalog registration](../catalog/README.md). Context manager does not construct Providers or read keys. See [Lab limitations](../ALGORITHM_AUDIT.md) for I/O and composition boundaries.

```bash
.venv/bin/python -m unittest tests.lab.test_context_pipeline tests.lab.test_information_sources tests.lab.test_rlm tests.lab.test_reduction_safety -v
```

[Memory resources](resources/README.md) provide session-scoped public history and immutable artifacts for working memory. They are infrastructure, not a selectable context stage.
[registration.py](registration.py) supplies typed parameter declarations without a discovery registry.
