# RSI Runtime Tests

[Up: Tests](../README.md)

Verify callback generations, candidate/parent/policy binding, activation
confirmation, cancellation and recovery of current job conditions.

| Files | Protects |
|---|---|
| `test_callbacks.py` | Proposal, verification, activation and next-generation improver binding |
| `test_recovery.py` | Activation reconciliation and unknown-work rejection |

```bash
.venv/bin/python -m tests --area rsi
```

Fake hosts establish transitions and accounting. Complete persistent host paths
remain in [Workflows](../workflows/README.md).
