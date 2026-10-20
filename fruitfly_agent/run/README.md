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

Interactive recovery displays original saved conversation through the same history component for both entry points. Startup selects the latest available non-empty session in the workspace. The picker shows unavailable files with reasons. Both paths use the selected current configuration and continue the original file without tool/model replay.

## Modules and ownership

| Module | Owns | Limits |
|---|---|---|
| [Configuration](configuration/README.md) | YAML, drafts, selection, model setup, and save/reset | No Provider construction or search |
| [Runtime](runtime/README.md) | Assembly, manifest, preparation, recovery, and permission bindings | Application owns lifecycle and switching |
| [Storage](storage/README.md) | Text artifacts, candidate records, result exports, retention | No quality decisions or activation |
| [Improvement host](improvement/README.md) | Search jobs, candidate rules, evolution capabilities, startup choices | Lab owns algorithms and the RSI state machine |
| [Learning host](learning/README.md) | Configured task observation and material persistence | No search or adoption authority |
| [Adapters](adapters/README.md) | Interactive views and optional Eval bridge | No algorithm-specific decisions |

[application.py](application.py) is the composition root. `RunApplicationFactory` constructs services, owns active runtime bindings, and delegates operations. Search services own preview receipts, startup services own choice receipts, and configuration owns its draft. Services use injected queries and operations instead of receiving the Factory or inspecting private fields.

## Public composition entries

| Entry | Responsibility |
|---|---|
| [__init__.py](__init__.py) | Stable Run exports |
| [cli.py](cli.py) | Startup arguments, frontend connection, and process exit |
| [application.py](application.py) | RuntimeFactory interface and concrete service composition |
| [assembly.py](assembly.py) | Public assembly/manifest/prompt-resolution exports |
| [profiles.py](profiles.py) | Configuration controller composed with candidate-backed prompt views |
| [evolution.py](evolution.py) | Bind Application and storage operations to the evolution host |
| [evaluation.py](evaluation.py) | Bind host queries to the optional Eval adapter |
| [startup_versions.py](startup_versions.py) | Public startup-selection composition entry |
| [migrate_improvement.py](migrate_improvement.py) | Explicit offline data/configuration migration; see [configuration](../../CONFIGURATION.md#relocate-improvement-data) |
| [migrate_configuration.py](migrate_configuration.py) | Explicit migration function and CLI; see [commands and limits](../../CONFIGURATION.md#relocate-workspace-configuration) |

Composition entries delegate to one owning implementation. Internal consumers import the owning module. Run consumes public [Catalog](../lab/catalog/README.md) and [Improvement](../lab/improvement/README.md) contracts; it does not implement search, scoring, or concrete algorithm branches.

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

[runtime/recovery.py](runtime/recovery.py) owns discovery and manifest checks. The existing exports from `run.application` remain available.

| Concern | Rule |
|---|---|
| RuntimeManifest | Schema 5 records assembled model/transport, mechanisms, prompt, artifacts, and current permissions. |
| History validation | Validate each saved manifest against its own digest and validate messages/projections. Known schema 3/4/5 contents remain readable; missing newer fields are not fabricated. |
| Configuration changes | Model/profile names, transport, prompts, permissions, and mechanism changes do not by themselves block continuation. Use the selected current configuration. |
| Environment recording | Append a complete snapshot after startup succeeds when the environment changes. Runs belong to the most recent preceding snapshot; original records remain intact. |
| Context changes | Rebuild the projection from canonical messages when mechanisms change; record it atomically with the environment snapshot. This does not count as a compaction. |
| Required material | Validate current artifact bindings and selected components' RecoveryValidator dependencies. Unused historical bindings do not force restoration. |
| Permissions | Apply current host policy with a fresh approval service. Historical grants are never replayed. |
| Failure | Corrupt data, writer locks, invalid current configuration, or unavailable required dependencies reject recovery with a reason. Failed startup does not append a runtime snapshot. |
| Activation | Improvement/RSI parent identity checks remain enforced to prevent stale activation. |
| State | Restore stored conversation/projections and explicit supported dependencies; no arbitrary heap restoration or paid-call replay. |

Canonical data and record semantics belong to [Session](../core/session/README.md). Configuration format belongs to [Harness configuration](configuration/README.md).

## Candidate jobs

[improvement/pipeline.py](improvement/pipeline.py) owns preview receipts and uses public stage factories, components, task, storage and active-version queries. The Factory retains active bindings and exposes the public host methods.

| Step | Run's responsibility |
|---|---|
| Preview | Bind one-use token to target, direction, task material, and parent manifest. |
| Start | Recheck source identity before model work, then freeze the job. |
| Execute | Run the injected `WorkflowController` through public stage contracts. |
| Save | Persist the preferred complete proposal, artifacts, task identity, and evidence. |
| Review | Map results to Interactive sections without parsing strategy-specific logs. |
| Activate | Prepare a separate handle; commit host references only after successful startup. |
| Retain | Protect configuration, Session, candidate-parent, and RSI references. |

The terminal edits one experiment panel and exposes scoped run history through the improvement service. Submitted jobs receive summaries even when cancelled before execution or completed without a candidate; native reports retain measured usage, stopping reasons and verified journal references. History protects referenced candidates without relaxing activation checks.

Component and generator views declare capability availability. Typed workflow requests select materials, component scope, exploration, allocations and optional feedback. Adding an implementation does not add algorithm branches to Run or the terminal.

Task selection does not change runtime configuration. Lab owns pack parsing and training edits. Readable `latest.txt` exports are not runtime inputs. Failed replacement retains the active runtime; external writes and effects do not automatically roll back. See [Improvement results](../lab/improvement/README.md#results-and-retention).

## Explicit text evolution

For a started Application with an available improver, an embedding host can inject an independent asynchronous verifier:

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

[runtime/permissions.py](runtime/permissions.py) constructs the standard file policy and minimal process environment. `build_runtime(..., permission_policy=None)` and `RunApplicationFactory(..., permission_policy=None)` accept an optional host-owned `PermissionPolicy`, exported by Lab Catalog. Its workspace must match the runtime workspace. Defaults allow ordinary workspace reads/writes, protect known credentials, and require confirmation for external paths and local execution.

After Lab installation, Run applies the policy to the final config and environment. It creates a fresh Interactive authorization service, binds it to Session frontend events, and protects the active Session file from tool writes. The normalized effective policy enters `RuntimeManifest.permissions` as a record of the active environment. Recovery uses current policy even when the historical policy differs or is absent. The current Session path is an additional per-handle protection, not part of reusable policy identity.

The optional [SSH environment](../lab/environment/ssh/README.md) supplies remote
path authorization and records `ssh-permissions-v1` instead of local file roots.
Remote execution prompts identify the server and port. Local extra roots and
Session protections do not become remote path rules; SSH account/password values
use the same host secret resolver as API keys and never enter runtime identity.

Only host constructor parameters select additional roots and protection paths. Model-edited profile files do not expand permission scope. Algorithm configuration/state remains accessible within authorized roots. User-driven model setup continues to persist credentials through its owning host interface, and Provider construction can obtain its required key. Shell/IPython do not receive those keys automatically.

Authorization audit entries contain call/tool identity, operation, outcome, and reason; they omit command/code contents, key values, and approval caches. Host policy must name additional credential files it uses. RuntimeManifest identities describe policy settings, not OS isolation or plugin source verification.

## Start an original-task improvement experiment

Use `/improvement` to select a saved task package or a bounded benchmark task set. One explicitly confirmed benchmark job prepares original material and freezes source, H/I/S, profile, model catalog, registered text state and original task bytes; its own baseline and official verification determine improvement. It does not silently start when configuration is enabled. A confirmed candidate uses the existing human review and fresh-session adoption path. See [Original task experiments](../lab/improvement/README.md) for budgets, splits, artifacts and unsupported targets. The public [trial.py](trial.py) composition entry runs one injected isolated task through the normal Application; Eval remains optional.
