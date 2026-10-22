# Algorithm Contracts

[Up: Lab](../README.md)

Identify algorithms and connect named text targets to shared search and adoption services.

| File / contract | Responsibility |
|---|---|
| [__init__.py](__init__.py): `AlgorithmSpec` | Algorithm ID, implementation ID, and state scope |
| `Algorithm` | Identity only; the relevant protocol determines execution. |
| [targets.py](targets.py): `TextTarget` | Snapshot, validate, and prepare a candidate trial |
| [components.py](components.py): `ComponentTarget` | Combine object-owned instruction adapters and retain separate bindings |
| [Improvement](../improvement/README.md) | Frozen problems, search services, observations, and results |
| [RSI](../rsi/README.md) | Explicit verification and adoption across generations |

## Add a text target

| Step | Action |
|---|---|
| 1 | Implement `snapshot`, `validate`, and `prepare_trial` in the object's module. |
| 2 | Register a `text-target:ID` component and declare any artifact slots. |
| 3 | Use the shared improvement, review, and activation path. |

Targets may expose an optional readable `label` for frontend selection; built-in targets do. Run falls back to the stable target ID for existing embeddings. Labels are presentation metadata and do not enter target/version identity. Target IDs remain available in experiment details.

`prepare_trial` projects a candidate into a temporary Core configuration. H prompt,
tool and catalog guidance use their object-owned adapters. I editor instructions
require an explicit improver-comparison runner. Declared roles do not supply an
execution capability automatically.

[retained.py](retained.py) provides immutable `RetainedText` S adapters for Skill and memory documents. `state_artifact_path(key)` in the public target contract identifies their virtual snapshot location. Sources expose `artifact_key`, `freeze()` and `freeze_text(text)` for exact prepared-runtime state verification. Overlapping source snapshots must agree on shared file contents. They do not write these virtual files in the production workspace.

The native runner projects all supported H/S adapters, including unchanged baseline documents. An optional `prepare_execution(config, text)` runs after host isolation and Provider budgeting; [Workflow](../workflow/README.md) uses this to install bounded stages. The adapter must preserve the supplied model/Provider and isolated Session/tool/environment boundary. Native scoring uses the final stage answer. [Retained target tests](../../../tests/lab/test_retained_targets.py) exercise production/trial agreement and root budgets.

No independent configuration, secrets, or model requests.

## Improve multiple instruction components

`ComponentTarget` exposes a flat set of registered text adapters with independent
H/S/I roles. Its canonical JSON maps exact component IDs to full strings. IDs and
bindings must be distinct; nesting, omitted IDs and unknown IDs fail. The complete
document has a 2 MB allocation and changed leaves use their owner's validator.
Unchanged large baseline guidance can remain registered.

The [Improvement registry](../improvement/README.md) exposes editable file sets and
retains exact owner metadata. Run builds one `component-bundle` from registered text
owners for publication, expanding actual changes into ordinary prompt/artifact
bindings. Trials, adoption and recovery reuse the same object installers. Tool
schemas, implementations and permissions remain owner-controlled. Mixed H/S edits
require runner support; I needs an improver-comparison runner. Arbitrary executable
source replacement is not installed.

```bash
.venv/bin/python -m unittest tests.workflows.test_decoupling -v
```

## Bind execution, improvement and persistent state

[versions.py](../improvement/contracts/versions.py) defines immutable `SystemVersion(harness, improver, state)`, `SnapshotFile` and `StateSnapshot`. References use SHA-256 content identities; model, permission, verifier, budget and environment conditions remain outside the modifiable triple. [candidates.py](../improvement/contracts/candidates.py) binds a modification set to its exact parent. Declared H/I/S roles must match the axes that changed; `TargetRegistry` rejects unregistered role/target/schema adapters.

[snapshots.py](snapshots.py) freezes bounded registered workspace text dependencies. Catalog exposes snapshot sources through `persistent-state-snapshots`; dynamic dependencies can declare `experiment-blockers`. Snapshots record roots even when empty. They bind initial-state identity; native trials receive only explicitly selected task files, not an automatic copy of these directories. Arbitrary plugin objects are not captured. The [component host](../improvement/README.md) supports registered executable H/S text components. I comparison uses the registered editor experiment; executable source changes require additional execution and verification adapters.

```bash
.venv/bin/python -m unittest tests.lab.test_experiment_contracts -v
```
