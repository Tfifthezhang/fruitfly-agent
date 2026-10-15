# Algorithm Contracts

[Up: Lab](../README.md)

Identify algorithms and connect named text targets to shared search and adoption services.

| File / contract | Responsibility |
|---|---|
| [__init__.py](__init__.py): `AlgorithmSpec` | Algorithm ID, implementation ID, and state scope |
| `Algorithm` | Identity only; the relevant protocol determines execution. |
| [targets.py](targets.py): `TextTarget` | Snapshot, validate, and prepare a candidate trial |
| [Optimization](../optimization/README.md) | Frozen problems, search services, observations, and results |
| [RSI](../rsi/README.md) | Explicit verification and adoption across generations |

## Add a text target

| Step | Action |
|---|---|
| 1 | Implement `snapshot`, `validate`, and `prepare_trial` in the object's module. |
| 2 | Register a `text-target:ID` component and declare any artifact slots. |
| 3 | Use the shared optimization, review, and activation path. |

`prepare_trial` projects a candidate into a temporary Core configuration, so search need not recognize target names. Current targets use `text-v1`: [Base prompt](../base_prompt/README.md) and [Skill guidance](../context_manager/augmentation/skills/README.md). Code and arbitrary stateful targets are unsupported.

No independent configuration, secrets, or model requests.

```bash
.venv/bin/python -m unittest tests.workflows.test_decoupling -v
```

## Bind execution, improvement and persistent state

[versions.py](versions.py) defines immutable `SystemVersion(harness, improver, state)`, `SnapshotFile` and `StateSnapshot`. References use SHA-256 content identities; model, permission, verifier, budget and environment conditions remain outside the modifiable triple. [candidates.py](candidates.py) binds a modification set to its exact parent. Declared H/I/S roles must match the axes that changed; `TargetRegistry` rejects unregistered role/target/schema adapters.

[snapshots.py](snapshots.py) freezes bounded registered workspace text dependencies. Catalog exposes snapshot sources through `persistent-state-snapshots`; dynamic dependencies can declare `experiment-blockers`. Snapshots record roots even when empty and trials receive independent copies. Arbitrary plugin objects are not captured. The [original-task experiment host](../optimization/experiments/README.md) currently changes H base prompt only. Workflow/code, I and S changes require explicit target and comparison implementations.

```bash
.venv/bin/python -m unittest tests.lab.test_experiment_contracts -v
```
