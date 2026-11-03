# Observe Runtime Operations

[Up: Core](../README.md)

Observe runtime facts independently of algorithms, frontends and Eval. Observation
does not retry, cancel, extend budgets or establish task correctness.

| Entry | Responsibility |
|---|---|
| `FailureInfo` in [models.py](models.py) | Origin, phase, evidence kind, cause code, effect uncertainty and retry disposition |
| `OperationEvent` | Immutable start/completion facts with run, parent, request and tool identities |
| `operation` in [scope.py](scope.py) | Task-local parent correlation and monotonic durations |
| `start_operation` | Generator/background lifetimes without retaining a ContextVar token across yields |
| [validation.py](validation.py) | Bounded identifiers, state and finite numeric validation |

Core records request preparation, context stages, model requests and tool work.
Providers and Lab add their own phases through the same public seam. Concrete
classification stays with the source owner. `FatalError`, `RetryableError` and
`OverflowError` retain control-flow authority; a diagnostic label grants none.

`AgentLoopConfig.on_observation` is an optional synchronous passive sink. Ordinary
sink failures are isolated. The standard loop also persists events through the
[Session codec](../session/observations.py). Writer failure is checked before the
next model request. Events contain identifiers and structured causes, never
arguments, prompts, response bodies, headers or credentials.

Durations use a monotonic clock. Completed stage totals can overlap. The public
Session summary reports their interval union separately, grouped by process clock.
Started operations without completion remain unfinished with unknown duration;
missing old observations are unknown rather than reconstructed. Live asyncio tasks
and unknown external effects are never replayed from observations.

```bash
.venv/bin/python -m unittest tests.core.test_observation tests.core.test_session_run_records
```

`FailureCause` retains at most six exception types, structural codes and optional
errno values; `FailureInfo` can retain an HTTP status. Text bodies remain excluded.
Untrusted correlation IDs that violate the bounded identifier grammar use stable
opaque hashes; observation never rejects a tool merely for its external call ID.
