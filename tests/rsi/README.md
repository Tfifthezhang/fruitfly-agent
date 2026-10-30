# RSI Runtime Tests

[Up: Tests](../README.md)

Verify callback generations, candidate/parent/policy binding, activation
confirmation, cancellation and recovery of root allowances.

| Files | Protects |
|---|---|
| `test_callbacks.py` | Proposal, verification, activation and next-generation improver binding |
| `test_recovery_budget.py` | Durable allocation restoration and unknown-work rejection |

```bash
.venv/bin/python -m tests --area rsi
```

Fake hosts establish transitions and accounting. Complete persistent host paths
remain in [Workflows](../workflows/README.md).
