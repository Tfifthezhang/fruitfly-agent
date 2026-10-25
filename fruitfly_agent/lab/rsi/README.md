# RSI

[Up: Lab](../README.md)

Coordinate proposal, independent verification, adoption, and continued improvement across versions. The host supplies capabilities and binds versions to actual implementations.

## Relationship to Improvement

| Layer | Question | Authority |
|---|---|---|
| Target module | What changes, and how does it run? | Defines snapshots and valid changes. |
| [Improvement](../improvement/README.md) | How are better candidates found? | Searches and reports evidence. |
| RSI driver | Which verified version runs next? | Coordinates an injected host and adoption policy. |
| [Run](../../run/README.md) / Application | How is a candidate stored and activated? | Persists identity and safely switches runtimes. |

Improvement does not require RSI. Human adoption alone is not a complete RSI loop. A self-improvement process targets its own harness or improver and uses the adopted version in subsequent generations.

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
| Rejected / failed verification | Do not adopt. The persistent driver stops on rejection by default. |
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

Use the independent [experiment CLI](../../experiments/README.md):
`fruitfly-agent-lab rsi check` then explicit `rsi run`. File defaults provide a
finite shared budget and three-generation limit. The command activates only
independently verified candidates into its experiment configuration copy, never
the daily or baseline profile. No background Catalog mechanism starts evolution.
Real capabilities may incur charges. The [Run host example](../../run/README.md#explicit-text-evolution)
also supports explicit integration without requiring Eval.

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

## Evolve the editor across generations

Use [editor-comparison material and requests](../improvement/improver/README.md).
The outer job changes I only; each inner trial fixes I and changes declared H/S.
Only the verified I artifact is activated. Runtime construction rebinds its exact
instruction bytes, and the next generation uses that active editor.

`RunEvolutionHost(application, factory, policy_id="improver-paired-v1", request=request)`
reuses an exact completed proof when `verify` is omitted. This requires a built-in
independent receipt; development scores, selected outputs and legacy candidates
without proof are rejected. It does not spend an additional private-suite use.
The suite must have a declared remaining use for each new generation. Explicit
custom verifier callbacks remain supported.

[Offline editor evolution tests](../../../tests/workflows/test_editor_evolution.py)
exercise actual inner editor calls, independent measurement, two I activations,
proof reuse and restart behavior without keys or network access. Their synthetic
response model is not evidence of real recursive capability gains.

## Configure continuation and stopping

Improvement searches one frozen experiment; RSI adopts eligible changes and
continues across generations. Eval is an optional execution/official-result
adapter, not an RSI dependency. `eval run` never starts evolution implicitly.

Both drivers use `controller.py` for generation accounting and consume pure
[termination policies](../improvement/termination/README.md). `EvolutionDriver`
accepts `stop_policy` and returns `stop_reason`. Its verification may carry an
optional finite score. Rejected proposals retain the parent and bounded feedback.

`PersistentEvolutionDriver.evolve` accepts `continue_on_rejection` and `stop_policy`.
The default still stops on rejection; opting in continues until a declared
condition or step limit. Persisted schema 2 records strategy identity, no-gain and
failure counters and stop reason. Schema-1 jobs remain readable. Changed strategy
rejects continuation; uncertain proposing/verifying work is never replayed.

For one allowance across generations, pass a root `BudgetScope` as `budget` to
`RunEvolutionHost`. Child jobs share it and return unused quota. Without this
optional embedding capability, legacy per-job allowances and step limits remain;
they do not constitute a global model/monetary limit. Custom verifier callbacks
must use their explicitly supplied accounting capability. Built-in completed
proof reuse makes no additional model request.

Online assessment may stop a probe through a declared control policy. It cannot
silently change the active H/S/I or grant independent adoption. Component changes
remain boundary-scoped; arbitrary code hot replacement is not implemented.

```bash
.venv/bin/python -m unittest tests.lab.test_evolution_policies tests.workflows.test_evolution tests.workflows.test_editor_evolution
```

Durable roots retain charged usage and absolute deadlines. Resume restores them
before another proposal and rejects changed limits. Unknown interrupted paid phases
forfeit the remaining allowance conservatively and stay interrupted; this does not
claim those requests actually occurred. Active coordinator elapsed time is retained;
absolute root deadlines also include downtime.
