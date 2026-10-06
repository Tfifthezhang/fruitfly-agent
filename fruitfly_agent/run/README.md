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

## Files and ownership

| File / module | Responsibility |
|---|---|
| [Configuration](configuration/README.md) | Harness YAML, validation, persistence, and digest |
| [profiles.py](profiles.py) | Catalog discovery and next-session configuration controller |
| [assembly.py](assembly.py) | Provider construction, Lab assembly, and actual manifest |
| [application.py](application.py) | `RunApplicationFactory`, runtime preparation, and recovery |
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

| Concern | Rule |
|---|---|
| RuntimeManifest | Schema 5 fixes actual model, effective selections/parameters, declared implementation identities, prompt content, and consumed artifacts. |
| Resume | Reload artifacts, verify hashes, and compare the complete manifest. |
| Built-in prompt changes | A different reference or text hash requires a new session; do not substitute new instructions into an existing Session. |
| Catalog changes | Unused model entries do not affect identity; changed active implementation or text does. |
| Compatibility | Accepted only when original prompt provenance and the rest of assembly can be established; never overwrite the stored manifest. |
| Configuration edits | Apply to a new session; do not relabel the active runtime. |
| Source / state | No source hot reload, source snapshot, arbitrary heap restoration, or paid-call replay. |

Canonical data and record semantics belong to [Session](../core/session/README.md). Configuration format belongs to [Harness configuration](configuration/README.md).

## Candidate jobs

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

Run has no dedicated API-key variables. Use [Configuration](../../CONFIGURATION.md) and [Providers](../providers/README.md) for environment handling.

```bash
.venv/bin/python -m unittest discover -s tests/run -t . -v
```
