# Run

[Up: Runtime Architecture](../README.md)

Assemble the default runtime from configuration, Providers, Lab, and Interactive. Run is the composition root; other runtime layers do not depend on it.

## Start from the CLI

```bash
.venv/bin/python -m fruitfly_agent --help
.venv/bin/python -m fruitfly_agent
.venv/bin/python -m fruitfly_agent "Summarize the Python files in this directory."
.venv/bin/python -m fruitfly_agent --resume
```

Real tasks call the configured model service and may incur charges. See [Getting started](../../GETTING_STARTED.md) for installation and [Terminal](../interactive/terminal/README.md) for interaction.

| Resume entry | Behavior |
|---|---|
| `--resume` | Resume the latest non-empty session at startup, subject to full runtime validation. |
| `--resume --session PATH` | Select the startup session explicitly. |
| `/resume` / `/resume PATH` | Choose or switch a session from an idle terminal. |
| `"TASK" --resume [--session PATH]` | Execute one new task with saved context; historical chat is not printed. Model requests may incur charges. |

Interactive recovery displays original saved conversation through the same terminal history component for both entry points. Startup selection uses the configured workspace/profile; incompatible sessions are rejected rather than silently skipped. In-terminal discovery lists compatible candidates. Neither entry merges sessions or replays model/tool execution.

## Files and ownership

| File / module | Responsibility |
|---|---|
| [Configuration](configuration/README.md) | Harness YAML, validation, persistence, and digest |
| [profiles.py](profiles.py) | Next-session draft editing, dependency changes, and persistence |
| [model_selection.py](model_selection.py) | Harness discovery and model catalog resolution |
| [migrate_configuration.py](migrate_configuration.py) | Explicit offline configuration relocation; see [commands and limits](../../CONFIGURATION.md#relocate-workspace-configuration) |
| [model_setup.py](model_setup.py) | Stage model additions and credentials, preserve local file contents, and coordinate save/rollback |
| [configuration_views.py](configuration_views.py) | Mechanism, algorithm-group, and prompt menu projections |
| [assembly.py](assembly.py) | Provider construction, Lab assembly, and actual manifest |
| [application.py](application.py) | `RunApplicationFactory`, runtime preparation, and candidate activation |
| [search_jobs.py](search_jobs.py) | Preview receipts, frozen search inputs, and proposal persistence |
| [recovery.py](recovery.py) | Session discovery, saved prompt/artifact references, and full manifest verification |
| [optimization.py](optimization.py) | Candidate records and durable inbox |
| [optimization_service.py](optimization_service.py) | Generic Interactive views and candidate preparation |
| [retention.py](retention.py), [task_results.py](task_results.py) | Reference-protected cleanup and readable exports |
| [startup_versions.py](startup_versions.py) | Optional version selection service for embedding hosts |
| [evolution.py](evolution.py) | Explicit verifier and durable evolution host |
| [evaluation.py](evaluation.py) | Optional Eval subprocess bridge; no top-level Eval import |
| [cli.py](cli.py) | Startup arguments and process exit |

Run consumes public [Catalog](../lab/catalog/README.md) and [Optimization](../lab/optimization/README.md) contracts. It does not implement search, task policies, scoring, or concrete algorithm branches.

## Text artifacts

This example stores text and creates a factory; it does not assemble a runtime or call a model:

```python
import os
from pathlib import Path
from fruitfly_agent.run import DataArtifactStore, RunApplicationFactory
from fruitfly_agent.lab.context_manager.augmentation.skills.target import SKILL_CATALOG_GUIDANCE_KEY

workspace = Path.cwd()
artifact = DataArtifactStore(workspace / ".fruitfly" / "artifacts").put_text(
    "Read relevant code and tests before answering; report how you verified the result."
)
factory = RunApplicationFactory(
    cwd=workspace,
    environment=dict(os.environ),
    data_artifact_bindings={SKILL_CATALOG_GUIDANCE_KEY: artifact.artifact_id},
)
```

| Binding | Behavior |
|---|---|
| `profile.prompt` | Built-in or content-addressed base prompt |
| `profile.artifact_bindings` | Declared named text slots |
| Constructor bindings | Fixed overrides; conflicting candidate activation is rejected. |
| Artifact contents | Plaintext trusted model context; keep secrets out. |
| Lifetime | Deleting referenced contents prevents recovery; unowned hand-created artifacts are not swept. |

Assembly occurs at `factory.open()` or `Application.start()`. See the [offline Application example](../../examples/extensions/README.md) for complete execution.

## Recovery

[recovery.py](recovery.py) owns discovery and manifest checks. The existing exports from `run.application` remain available.

| Concern | Rule |
|---|---|
| RuntimeManifest | Schema 5 fixes actual model, normalized transport defaults/overrides and implementation identity when published by the Provider, effective selections/parameters, prompt content, and consumed artifacts. |
| Resume | Reload artifacts, verify hashes, and compare the complete manifest, including transport policy. A manifest missing a matching transport identity is rejected; do not overwrite or silently adopt new defaults. |
| Built-in prompt changes | A different reference or text hash requires a new session; do not substitute new instructions into an existing Session. |
| Catalog changes | Unused model entries do not affect identity; changed active implementation or text does. |
| Compatibility | Accepted only when original prompt provenance and the rest of assembly can be established; never overwrite the stored manifest. |
| Configuration edits | Apply to a new session; do not relabel the active runtime. |
| Source / state | No source hot reload, source snapshot, arbitrary heap restoration, or paid-call replay. |

Canonical data and record semantics belong to [Session](../core/session/README.md). Configuration format belongs to [Harness configuration](configuration/README.md).

## Candidate jobs

[search_jobs.py](search_jobs.py) coordinates previews and searches against the factory's active runtime. The factory retains runtime ownership and exposes the existing host methods.

| Step | Run's responsibility |
|---|---|
| Preview | Bind one-use token to target, direction, task material, and parent manifest. |
| Start | Recheck source identity before model work, then freeze the job. |
| Search | Call generic `TextOptimizer.search(text, direction, parent_manifest=..., task=...)`. |
| Save | Persist the preferred complete proposal, artifacts, task identity, and evidence. |
| Review | Map results to Interactive sections without parsing strategy-specific logs. |
| Activate | Prepare a separate handle; commit host references only after successful startup. |
| Retain | Protect configuration, Session, candidate-parent, and RSI references. |

Task selection does not change runtime configuration. Lab owns pack parsing and training edits. Readable `latest.txt` exports are not runtime inputs. Failed replacement retains the active runtime; external writes and effects do not automatically roll back. See [Optimization results](../lab/optimization/README.md#results-and-retention).

## Explicit text evolution

For a started Application with an enabled optimizer, an embedding host can inject an independent asynchronous verifier:

```python
from fruitfly_agent.lab.rsi import PersistentEvolutionDriver
from fruitfly_agent.run.evolution import RunEvolutionHost

# application, factory, and verify_candidate are supplied by the host.
host = RunEvolutionHost(
    application, factory,
    policy_id="my-fixed-policy-v1", verify=verify_candidate,
)
# In the host's event loop, after explicitly authorizing model work:
# result = await PersistentEvolutionDriver().evolve(
#     host, job_id="text-evolution-1", policy_id="my-fixed-policy-v1",
#     direction="Improve the fixed task", max_steps=2, phase_timeout_seconds=60,
# )
```

The verifier returns `VerificationEvidence` bound to candidate/artifact/parent/policy identities, not merely a search score. Jobs live in `.fruitfly/evolution/`. Only confirmed activation advances the version. Unknown paid phases stop; activation interruptions reconcile the actual manifest. One coordinator owns the job; no cross-process commit transaction. See [RSI](../lab/rsi/README.md).

Run exposes an optional `configuration.model_setup` service to the terminal. Model additions and hidden credentials stay in memory until configuration save; reset discards them. The factory's secret environment is updated after successful save, so the next session can use the model without restarting. Existing configuration-controller consumers can omit this service. Use [Configuration](../../CONFIGURATION.md) and [Providers](../providers/README.md) for supported APIs, generated key-variable names, and persistence limits.

```bash
.venv/bin/python -m unittest discover -s tests/run -t . -v
```

## Bind host permission policy

[permissions.py](permissions.py) constructs the standard file policy and minimal process environment. `build_runtime(..., permission_policy=None)` and `RunApplicationFactory(..., permission_policy=None)` accept an optional host-owned `PermissionPolicy`, exported by Lab Catalog. Its workspace must match the runtime workspace. Defaults allow ordinary workspace reads/writes, protect known credentials, and require confirmation for external paths and local execution.

After Lab installation, Run applies the policy to the final config and environment. It creates a fresh Interactive authorization service, binds it to Session frontend events, and protects the active Session file from tool writes. The normalized effective policy identity enters `RuntimeManifest.permissions`; recovery compares it with the rest of the manifest. Missing or changed permission identities do not silently resume. The current Session path is an additional per-handle protection, not part of reusable policy identity.

Only host constructor parameters select additional roots and protection paths. Model-edited profile files do not expand permission scope. Algorithm configuration/state remains accessible within authorized roots. User-driven model setup continues to persist credentials through its owning host interface, and Provider construction can obtain its required key. Shell/IPython do not receive those keys automatically.

Authorization audit entries contain call/tool identity, operation, outcome, and reason; they omit command/code contents, key values, and approval caches. Host policy must name additional credential files it uses. RuntimeManifest identities describe policy settings, not OS isolation or plugin source verification.
