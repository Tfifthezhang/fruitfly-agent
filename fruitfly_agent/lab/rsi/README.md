# RSI Experiment Defaults

[Up: Lab](../README.md)

Declare finite experiment settings for the independent [RSI runtime](../../rsi/README.md).
This module owns no generation loop. Concrete stopping mechanisms use the existing
[Execution control](../improvement/stages/control.py).

| Entry | Behavior |
|---|---|
| `configuration.py`: `EvolutionSettings` | Generation count, continuation and verification policy |
| Generic embedding | Inject proposal, verification and activation explicitly; no automatic Improvement CLI composition |

The generic host accepts explicit capabilities. Independent Improvement stages
remain separate operations and do not start evolution. Configuration snapshots
and candidate research choices do not authorize activation.

```bash
.venv/bin/python -m unittest tests.rsi.test_recovery tests.experiments.test_operations
```

Offline fixtures establish orchestration behavior, not real model quality.

## Preserve parameter versions between generations

Every candidate parameter document retains its protected H/S/I role. Each
generation compares frozen effective parameters and initial state; owner-default
changes cannot silently enter an existing trial. Text and numeric edits use the
same declared grants and execution path. Verified activation selects immutable
changed component content while unrelated default references remain unchanged.
Parameter editing does not authorize implementation replacement or role changes.
