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
| `models.py` | Immutable callback versions, candidates, verification and independent phase times |

The transition path is ready, proposing, proposed, verifying, verified, activating,
then ready or a terminal phase. Attempts consume the generation limit even when
proposal or verification fails. The callback host can record recoverable failures;
durable hosts preserve uncertain phases and stop instead of replaying work.
Independent verification must bind candidate, parent and policy. Only confirmed
activation advances the incumbent. Planned adoption does not count as activation.
The next generation resolves the active improver again.

Core's operation supervisor provides cancellation and confirmed retirement. Composite Improvement jobs keep their independent editor, execution and evaluator times; RSI does not add a shared deadline or quota. The callback host applies `EvolutionBudget.timeouts` to its bare phase callbacks. Stop-policy parameters join persisted strategy identity.

## Recover without replay

Hosts provide `load_job`, `save_job`, `active_manifest` and `is_active`. Interrupted activation is reconciled against actual host identity. Interrupted proposing/verifying work remains interrupted; unknown requests are not replayed. Recovery accepts the current durable record schema and rejects changed job conditions.

[Improvement](../improvement/README.md) searches one frozen job; RSI decides which verified version is used in later generations. I experiments create fresh fixed-I studies. Leaf phases retain independent invocation times.

## Verify offline

```bash
.venv/bin/python -m unittest tests.rsi.test_callbacks tests.rsi.test_recovery tests.workflows.test_evolution tests.workflows.test_developer_extensions
```

Fake Providers verify execution binding, cancellation, continuation and recovery.
They do not establish capability gains. Trusted in-process callbacks must
cooperate with cancellation; source deployment, arbitrary heap restoration and
cross-process activation transactions are not implemented.
