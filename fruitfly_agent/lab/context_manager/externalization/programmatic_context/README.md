# Programmatic Context

[Up: Externalization](../README.md)

Inspect long context through a persistent IPython workspace, Session artifacts, and budgeted auxiliary model queries. This does not enlarge the Provider's physical context window.

## Enable and use

| Mechanism | Capability |
|---|---|
| `ipython-tool` | Python execution with a persistent runtime namespace |
| `rlm-ipython` | Context externalization; requires the IPython tool |

| Namespace API | Purpose |
|---|---|
| `context.list/stat` | Discover and inspect artifacts |
| `context.read/search` | Read or search stored content |
| `context.put` | Store content |
| `context.save_state/load_state` | Persist and restore explicit JSON state |
| `llm_query` | Query an injected auxiliary Provider; depth 1, with call/token budgets |

Run injects Providers and Session paths; this library does not read keys. IPython runs with local user permissions and is not a sandbox. `llm_query` uses the network and may incur charges. No user-facing module-specific environment variables.

## Research basis

Based on Zhang et al., [Recursive Language Models](https://arxiv.org/abs/2512.24601v3), Section 2. The paper treats input as an external programmable object and permits symbolic sub-model calls.

| Aspect | This implementation |
|---|---|
| External input | Content-addressed Session artifacts |
| REPL | Persistent IPython subprocess |
| Sub-calls | Text-returning queries at depth 1 |
| Recovery | Artifacts and explicit JSON state; no arbitrary heap restoration |
| Full paper behavior | No unrestricted recursive inference, variable-based unlimited final output, or reproduced benchmark gains |

## Files and contracts

| File | Responsibility |
|---|---|
| [artifacts.py](artifacts.py) | `ContextArtifact`, workspace, and Session artifact storage |
| [protocols.py](protocols.py) | `ContextArtifactWriter` boundary |
| [projection.py](projection.py) | `ProgrammaticContextExternalizer` |
| [runtime.py](runtime.py) | `IpythonRuntime` and execution results |
| [kernel.py](kernel.py) | Subprocess namespace and host requests |
| [query.py](query.py) | `ModelQueryBroker` and query configuration |

| Limit | Current behavior |
|---|---|
| Artifact slice reads | Load and verify the whole artifact before slicing. |
| Output | JSONL transport occurs before truncation; large lines may exceed transport limits. |
| Cancellation | Hard-cancel and host-request task cleanup are not unified. |
| Query timeout | Does not include semaphore queue time. |
| Token budget | Estimate/reservation with actual-usage reconciliation. |
| Reduction composition | Summarizing preserves externalized projections and references; new reducers must verify source mappings. |

Register subprocess resources immediately with `context.own` and expose them in assembly components. Define schema, serialization errors, reset, and cancellation for added state. See [Catalog](../../../catalog/README.md) and [Known limitations](../../../ALGORITHM_AUDIT.md).

```bash
.venv/bin/python -m unittest tests.lab.test_rlm -v
```

Tests use local IPython subprocesses, temporary artifacts, and a fake Provider; no real model requests.

`IpythonRuntime(process_environment=...)` uses an explicit child environment rather than copying `os.environ`. Standard assembly supplies the host's minimal execution environment and keeps Provider credentials in the host-side model query broker. Model-driven IPython calls require local execution authorization. This does not isolate Python file/network APIs; approved cells still run with current-user permissions.
