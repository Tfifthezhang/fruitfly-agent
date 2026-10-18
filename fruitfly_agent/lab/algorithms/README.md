# Algorithm Contracts

[Up: Lab](../README.md)

Identify algorithms and connect named text targets to shared search and adoption services.

| File / contract | Responsibility |
|---|---|
| [__init__.py](__init__.py): `AlgorithmSpec` | Algorithm ID, implementation ID, and state scope |
| `Algorithm` | Identity only; the relevant protocol determines execution. |
| [targets.py](targets.py): `TextTarget` | Snapshot, validate, and prepare a candidate trial |
| [Improvement](../improvement/README.md) | Frozen problems, search services, observations, and results |
| [RSI](../rsi/README.md) | Explicit verification and adoption across generations |

## Add a text target

| Step | Action |
|---|---|
| 1 | Implement `snapshot`, `validate`, and `prepare_trial` in the object's module. |
| 2 | Register a `text-target:ID` component and declare any artifact slots. |
| 3 | Use the shared improvement, review, and activation path. |

Targets may expose an optional readable `label` for frontend selection; built-in targets do. Run falls back to the stable target ID for existing embeddings. Labels are presentation metadata and do not enter target/version identity. Target IDs remain available in experiment details.

`prepare_trial` projects a candidate into a temporary Core configuration, so search need not recognize target names. H instruction targets use `text-v1`: [Base prompt](../base_prompt/README.md) and [Skill guidance](../context_manager/augmentation/skills/README.md). The [tree-search policy target](../improvement/methods/tree_search/README.md) uses `exploration-policy-v1` for a validated I JSON artifact. It requires search-level comparison rather than task-prompt projection. Code and arbitrary stateful targets remain unsupported.

[retained.py](retained.py) provides immutable `RetainedText` S adapters for Skill and memory documents. `state_artifact_path(key)` in the public target contract identifies their virtual snapshot location. Sources expose `artifact_key`, `freeze()` and `freeze_text(text)` for exact prepared-runtime state verification. Overlapping source snapshots must agree on shared file contents. They do not write these virtual files in the production workspace.

Targets may declare `project_in_trials` to retain their baseline document or execution when another target changes. An optional `prepare_execution(config, text)` runs after host isolation and Provider budgeting; [Workflow](../workflow/README.md) uses this to install bounded stages. The adapter must preserve the supplied model/Provider and isolated Session/tool/environment boundary. Native scoring uses the final stage answer. [Retained target tests](../../../tests/lab/test_retained_targets.py) exercise production/trial agreement and root budgets.

No independent configuration, secrets, or model requests.

```bash
.venv/bin/python -m unittest tests.workflows.test_decoupling -v
```

## Bind execution, improvement and persistent state

[versions.py](../improvement/contracts/versions.py) defines immutable `SystemVersion(harness, improver, state)`, `SnapshotFile` and `StateSnapshot`. References use SHA-256 content identities; model, permission, verifier, budget and environment conditions remain outside the modifiable triple. [candidates.py](../improvement/contracts/candidates.py) binds a modification set to its exact parent. Declared H/I/S roles must match the axes that changed; `TargetRegistry` rejects unregistered role/target/schema adapters.

[snapshots.py](snapshots.py) freezes bounded registered workspace text dependencies. Catalog exposes snapshot sources through `persistent-state-snapshots`; dynamic dependencies can declare `experiment-blockers`. Snapshots record roots even when empty and trials receive independent copies. Arbitrary plugin objects are not captured. The [original-task experiment host](../improvement/experiments/README.md) currently changes H base prompt only. Workflow/code, I and S changes require explicit target and comparison implementations.

```bash
.venv/bin/python -m unittest tests.lab.test_experiment_contracts -v
```
