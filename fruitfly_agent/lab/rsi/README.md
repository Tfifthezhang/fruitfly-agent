# RSI Experiment Defaults

[Up: Lab](../README.md)

Declare finite experiment settings for the independent [RSI runtime](../../rsi/README.md).
This module owns no generation loop. Concrete stopping mechanisms use the existing
[Improvement termination contracts](../improvement/termination/README.md).

| Entry | Behavior |
|---|---|
| `configuration.py`: `EvolutionSettings` | Generation count, phase/root deadlines, model/execution allowances, continuation and verification policy |
| Experiment CLI | Explicit `rsi check` and `rsi run`; normal chat never starts evolution implicitly |

The [experiment host](../../experiments/README.md) applies one root allowance across
generations and activates into its experiment configuration copy. Independent
verification is required. Daily configuration is unchanged by that experiment.
[Run](../../run/README.md#explicit-text-evolution) also exposes a host for explicit
embedding. Eval remains an optional execution consumer.

```bash
.venv/bin/python -m unittest tests.lab.test_evolution_policies tests.experiments.test_operations
```

Offline fixtures establish orchestration behavior, not real model quality.
