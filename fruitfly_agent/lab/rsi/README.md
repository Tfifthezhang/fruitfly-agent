# RSI

[Up: Lab](../README.md)

Coordinate proposal, independent verification, adoption, and continued improvement across versions. The host supplies capabilities and binds versions to actual implementations.

## Relationship to Optimization

| Layer | Question | Authority |
|---|---|---|
| Target module | What changes, and how does it run? | Defines snapshots and valid changes. |
| [Optimization](../optimization/README.md) | How are better candidates found? | Searches and reports evidence. |
| RSI driver | Which verified version runs next? | Coordinates an injected host and adoption policy. |
| [Run](../../run/README.md) / Application | How is a candidate stored and activated? | Persists identity and safely switches runtimes. |

Optimization does not require RSI. Human adoption alone is not a complete RSI loop. A self-improvement process targets its own harness or improver and uses the adopted version in subsequent generations.

## Drivers

| API | Scope |
|---|---|
| `EvolutionDriver(generator_for=..., verify=..., adopt=..., policy_id=..., budget=...)` | Bounded single invocation with injected callbacks |
| `await driver.evolve(initial, feedback=..., signal=...)` | Generate, verify, adopt, and resolve the next generator |
| `PersistentEvolutionDriver.evolve(host, job_id=..., policy_id=..., direction=..., max_steps=2, phase_timeout_seconds=60)` | Host-owned durable text evolution |

| Rule | Behavior |
|---|---|
| Candidate | Must change an artifact reference and match the current parent. |
| Verification | Must match candidate identity and fixed policy. Search score alone is insufficient. |
| Rejected / failed verification | Do not adopt. The persistent driver stops on rejection. |
| Confirmed adoption | Resolve the active improver again for the next generation. |
| `planned` result | Does not advance the version; only `activated` does. |
| Adoption exception / timeout | Propagate; the host must reconcile external state rather than assume rollback. |

## State and limits

| Concern | Contract |
|---|---|
| Single-call defaults | 3 steps, 60 seconds per phase, feedback limited to 8000 characters |
| Persistent state | Injected `EvolutionHost` owns jobs, candidates, policy, and evidence. |
| Interrupted proposing/verifying | Mark interrupted and stop; do not replay unknown paid work. |
| Interrupted activation | Reconcile actual activated manifest; continue only after confirmed commit. |
| Cancellation | Cooperative signal plus task cancellation; no preemptive control over malicious Python. |
| Resolver | Fast, synchronous version lookup with no I/O |
| Budgets | Step limits do not enforce model, token, file, or monetary limits; injected capabilities do. |
| Coordination | One coordinator per incumbent/job; no cross-process transaction. |
| Unsupported | Source replacement, general code candidates, arbitrary Python heap or learning-state recovery |

There is no default autonomous CLI or Catalog mechanism. Real injected capabilities may incur charges. The [Run host example](../../run/README.md#explicit-text-evolution) shows explicit integration without requiring Eval.

## Files and verification

| File | Responsibility |
|---|---|
| [models.py](models.py) | Versions, candidates, verification, budgets, and outcomes |
| [driver.py](driver.py) | Generator/verifier/adopter orchestration |
| [persistent.py](persistent.py) | Durable orchestration through `EvolutionHost` |

```bash
.venv/bin/python -m unittest tests.lab.test_rsi tests.workflows.test_evolution -v
```

Offline tests verify binding, continuation, rejection, cancellation, budgets, and reconciliation. They do not prove real improvement or safe arbitrary code deployment. No module-specific environment variables.
