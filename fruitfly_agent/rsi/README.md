# RSI Runtime

[Up: Runtime Architecture](../README.md)

Run verified generations through one state machine. The kernel depends only on
Core, Improvement and its own contracts. It creates no models, editors, file
stores, benchmark adapters or production implementations.

## Run generations

| Entry | Responsibility |
|---|---|
| `engine.py`: `EvolutionEngine.evolve` | Shared proposal, verification, activation and continuation state machine |
| `contracts.py`: `EvolutionHost`, `EvolutionJob` | Injected effects and durable state, including exact parent and policy bindings |
| `state.py` | Generation accounting and injected soft stop decisions |
| `callbacks.py`: `EvolutionDriver` | In-memory callback host using the same engine; no separate loop |
| `models.py` | Immutable callback versions, candidates, verification and finite allowances |

The transition path is ready, proposing, proposed, verifying, verified, activating,
then ready or a terminal phase. Attempts consume the generation limit even when
proposal or verification fails. The callback host can record recoverable failures;
durable hosts preserve uncertain phases and stop instead of replaying work.
Independent verification must bind candidate, parent and policy. Only confirmed
activation advances the incumbent. Planned adoption does not count as activation.
The next generation resolves the active improver again.

All asynchronous phases use Core's bounded operation supervisor. Unconfirmed
retirement stops scheduling. Model/execution quota and the absolute deadline use
an injected shared Improvement `BudgetScope`. A step limit alone is not a monetary
or model-call allowance. Stop-policy parameters join persisted strategy identity.

## Recover without replay

Hosts provide `load_job`, `save_job`, `active_manifest` and `is_active`. An
interrupted activation is reconciled against actual host identity. Interrupted
proposing/verifying work remains interrupted; unknown requests are not replayed.
Root allowances, recursion limits and absolute deadlines survive restart.
A saved root allocation without its required recursion limit is rejected; changed
limits cannot authorize a resumed job. Durable schema versions
remain persistence protocols, independently of the single configuration grammar.

The [Run host](../run/README.md#explicit-text-evolution) owns activation and storage.
[Lab RSI defaults](../lab/rsi/README.md) supply finite experiment settings.
[Improvement](../improvement/README.md) searches one frozen job; RSI decides which
verified version is used in subsequent generations. I experiments use bounded
nested Improvement jobs, with child budgets rather than fresh root allowances.

## Verify offline

```bash
.venv/bin/python -m unittest tests.rsi.test_callbacks tests.rsi.test_recovery_budget tests.workflows.test_evolution tests.workflows.test_developer_extensions
```

Fake Providers verify execution binding, cancellation, continuation and recovery.
They do not establish capability gains. Trusted in-process callbacks must
cooperate with cancellation; source deployment, arbitrary heap restoration and
cross-process activation transactions are not implemented.
