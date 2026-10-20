# Lab

[Up: Runtime Architecture](../README.md)

Add tools, execution backends, context strategies, and improvement algorithms through Core's public contracts. Lab owns implementations and registration; Run assembles them and Application manages their lifetime.

## Choose a module

| Module | Responsibility |
|---|---|
| [Catalog](catalog/README.md) | Mechanism definitions, parameters, dependencies, and installers |
| [Algorithms](algorithms/README.md) | Algorithm identity and text-target contracts |
| [Context manager](context_manager/README.md) | Augmentation, externalization, and reduction |
| [Tools](tools/README.md) | Model-callable file, shell, IPython and public web operations |
| [Environment](environment/README.md) | Local filesystem and process backend |
| [Base prompt](base_prompt/README.md) | Built-in prompt text and its target adapter |
| [Workflow](workflow/README.md) | Bounded sequential execution and its H target |
| [Improvement](improvement/README.md) | Component workflow, task evidence, experience and optional verification |
| [Learning](learning/README.md) | Independently configured daily task-material production |
| [RSI](rsi/README.md) | Verified adoption and continuation across generations |
| [Known limitations](ALGORITHM_AUDIT.md) | Current budget, I/O, cancellation, and composition limits |

## Improvement and RSI

| Question | Owner | Example |
|---|---|---|
| What runs, and what can change? | Object module and target adapter | Base prompt or Skill catalog guidance |
| How are improvements proposed and compared? | Improvement | Replaceable generators propose evidence-based component edits. |
| Who verifies, adopts, and continues? | Human or explicit RSI host | Review one result, or run verified text evolution. |

Improvement runs independently of RSI. Its public stage contracts separate proposal, execution, composition, output selection, verification and reflection. Persistent RSI requires an explicit host and verification policy; only confirmed activation advances the deployed version.

Generators implement `CandidateGenerator`; `WorkflowBindings` injects replaceable stages. Existing H/S text owners reuse the same execution and adoption path. I edits require an explicit improver-comparison runner.

Task-local work can use execution evidence without answers or scores. Persistent candidates require independent verification before human adoption. Attributed experience is retained separately at task boundaries.

## Develop an algorithm

Start with the complete offline example:

```bash
.venv/bin/python -m examples.extensions.offline_guidance
```

It registers a context transformer, assembles it through Run, and submits a task through Application. See [the example](../../examples/extensions/README.md) before reading the detailed [Catalog contract](catalog/README.md#assembly-contract).

| Change | Extension point | Guide |
|---|---|---|
| Add request information | `ContextTransformer` | [Augmentation](context_manager/augmentation/README.md) |
| Move large content out of the projection | `ContextTransformer` plus retrievable references | [Externalization](context_manager/externalization/README.md) |
| Summarize or recover from overflow | `ContextReducer` | [Reduction](context_manager/reduction/README.md) |
| Retrieve a new information source | `InformationRetriever` and optional reader | [Information spaces](context_manager/augmentation/information/README.md) |
| Add an operation | `AgentTool` | [Tools](tools/README.md) |
| Replace file or shell access | `ExecutionEnv` | [Environment](environment/README.md) |
| Collect feedback or update experience | Active hook or passive observer | [Core extensions](../core/extensions/README.md) |
| Search candidates | `CandidateGenerator` and stage ports | [Improvement](improvement/README.md#extend-search) |
| Verify and adopt across generations | `EvolutionHost` and explicit policy | [RSI](rsi/README.md) |

## Implementation rules

| Concern | Required behavior |
|---|---|
| Dependencies | Import only Core and Lab; inject model, filesystem, network, and host capabilities. |
| Input ownership | Treat context frames and nested messages as read-only; return new projections or decisions. |
| State | Specify request, run, Session, or workspace scope; define reset and recovery behavior. |
| Budgets | State which calls, bytes, tokens, time, and queue waits are actually bounded. |
| Failure | Preserve protocol distinctions between no-op, ordinary failure, and cancellation. |
| Resources | Register owned resources during construction; clean up failed assembly and cancellation. |
| Registration | Declare parameters, contributions, dependencies, implementation identity, external effects, a concise distinguishing description, and implementation/guide paths. Mark necessary user inputs explicitly; keep tuning in YAML. |
| Verification | Observe useful output, disabled behavior, failure, cancellation, isolation, and recovery where applicable. |

Catalog checks declared parameters, dependencies, conflicts, stage shape, and returned assembly state. It does not prove deep immutability, resource budgets, algorithm quality, or every mechanism combination. Plain interface conformance is insufficient.

## Test and evaluate

```bash
.venv/bin/python -m tests --area lab --area workflows
.venv/bin/python -m unittest discover -s tests -t .
```

| Evidence | Scope |
|---|---|
| Offline regression | Public behavior, assembly, Application use, and resource handling |
| Live model checks | Actual model behavior; explicit network and cost authorization required |

Researchers manage formal experiments and their records externally. Learning mechanisms still define initial state, data splits, reset rules, and state sharing. A RuntimeManifest is not a source or learning-state snapshot. [Eval](../../eval/README.md) can consume public capabilities, but must not define their production interfaces.

Lab has no shared environment variables and does not read ambient API keys. Hosts inject credentials required by selected tools. [Configuration](../../CONFIGURATION.md) selects mechanisms; each child guide describes its own external effects.
