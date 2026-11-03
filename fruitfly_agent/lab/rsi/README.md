# RSI Experiment Defaults

[Up: Lab](../README.md)

Declare finite experiment settings for the independent [RSI runtime](../../rsi/README.md).
This module owns no generation loop. Concrete stopping mechanisms use the existing
[Improvement termination contracts](../improvement/termination/README.md).

| Entry | Behavior |
|---|---|
| `configuration.py`: `EvolutionSettings` | Generation count, continuation and verification policy |
| Experiment CLI | Explicit `rsi check` and `rsi run`; normal chat never starts evolution implicitly |

The [experiment host](../../experiments/README.md) activates into its experiment configuration copy after independent verification. Each editor, execution and evaluator invocation receives its own configured time. Usage is recorded across generations without a shared admission ledger. Daily configuration remains unchanged. [Run](../../run/README.md#explicit-text-evolution) also exposes explicit embedding.

```bash
.venv/bin/python -m unittest tests.lab.test_evolution_policies tests.experiments.test_operations
```

Offline fixtures establish orchestration behavior, not real model quality.

## Preserve parameter versions between generations

Every candidate parameter document retains its protected H/S/I role. Each
generation compares frozen effective parameters and initial state; owner-default
changes cannot silently enter an existing trial. Text and numeric edits use the
same declared grants and execution path. Verified activation selects immutable
changed component content while unrelated default references remain unchanged.
Parameter editing does not authorize implementation replacement or role changes.
