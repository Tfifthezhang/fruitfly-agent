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
