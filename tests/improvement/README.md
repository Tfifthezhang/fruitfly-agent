# Improvement Runtime Tests

[Up: Tests](../README.md)

Verify optimization admission, bounded scheduling, stage failures, immutable
hooks, resource retirement and hierarchical accounting. Concrete editor, scoring
and research mechanisms remain in [Lab tests](../lab/README.md).

| Files | Protects |
|---|---|
| `test_optimization.py` | Explicit owner declarations, capability/timing rejection and recursion allowances |
| `test_scheduler.py` | Queue bounds, cancellation and resource cleanup |
| `test_services.py` | Immutable hooks, cancellation, event tails and bounded long sequences |
| `test_reliability.py` | Stage failure retention, receipt identity, persistence and cleanup |

```bash
.venv/bin/python -m tests --area improvement
```

Use fake ports and deterministic fixtures. No real models or quality claims.
