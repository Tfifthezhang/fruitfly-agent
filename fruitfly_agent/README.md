# Runtime Architecture

[Up: FruitFlyAgent](../README.md)

FruitFlyAgent separates the Agent loop, model adapters, Application lifecycle, and replaceable algorithms. Run assembles them into an interactive runtime.

## Modules

| Module | Owns | Depends on |
|---|---|---|
| [Core](core/README.md) | Messages, loop, tools, context contracts, and Session persistence | Core only |
| [Providers](providers/README.md) | Model API requests, streaming, and error mapping | Core and Providers |
| [Interactive](interactive/README.md) | Application lifecycle, multi-turn state, events, and terminal | Core and Interactive |
| [Lab](lab/README.md) | Tools, environments, context strategies, improvement, and RSI | Core and Lab |
| [Run](run/README.md) | Configuration, Provider construction, assembly, and CLI | All runtime layers |
| [Eval](../eval/README.md) | Optional single-configuration benchmark execution and reports | Core, Providers, Lab, and Eval |

Eval consumes public runtime capabilities. Removing it must leave normal Agent use and algorithm development intact.

Independent improvement methods declare H/S/I support in method packages within Lab's [Improvement](lab/improvement/README.md#improvement-methods) module. They use shared search services and object-owned target adapters; Run assembles them without implementing algorithm-specific search logic.

Lab registrations own concise algorithm descriptions and implementation/guide paths.
Configuration and improvement menus consume this shared metadata, show necessary
user inputs and budgets, and leave internal tuning in configuration. Improvement
discovery excludes methods with incompatible target roles or formats before
checking runtime availability.

[Execution workflows](lab/workflow/README.md) own bounded H stage execution. Skill and memory adapters own retained S documents. Workflow search, Skill document optimization and Exploratory memory learning use these adapters, fixed comparison tasks, host-owned independent confirmation and the normal human adoption lifecycle. S artifacts enter state identity separately from H and I.

Optional [automatic text search](lab/improvement/automatic/README.md) separates original tasks, derived learning material and confirmation. [Failure processing](lab/improvement/failure_processing/README.md) is independently replaceable. A confirmed candidate enters human review; Application still owns activation. [Original task experiments](lab/improvement/experiments/README.md) freeze H/I/S, consume official task evidence and reuse this human adoption path.

Run separates [configuration](run/configuration/README.md), [runtime preparation](run/runtime/README.md), [storage](run/storage/README.md), [improvement hosting](run/improvement/README.md), and [adapters](run/adapters/README.md). Its Factory composes these services; leaf services receive explicit capabilities and own their local state.

Interactive separates Contracts, Application, Session, Interaction, and Terminal. It keeps lifecycle authority in Application and exposes independent search, candidate, and task material contracts. Its terminal uses [registered command handlers](interactive/terminal/README.md#register-a-command); feature flows consume explicit capabilities and share one input owner.

## Follow a request

| Step | Owner | Action |
|---|---|---|
| 1 | Run | Resolve configuration, construct the Provider, and assemble selected Lab components. |
| 2 | Application | Open the runtime and Session, start owned resources, and accept input. |
| 3 | Core | Record the user message and prepare the model context. |
| 4 | Context pipeline | Apply augmentation, externalization, and reduction. |
| 5 | Provider | Stream an assistant response into Core events and messages. |
| 6 | Core | Execute valid tool calls, record results, and continue or finish. |
| 7 | Application | Deliver frontend events and close resources when the runtime ends. |

The Session keeps canonical conversation facts. The model projection is the context sent to the Provider; it may contain additional information, external references, or summaries.

[DreamRSI](lab/improvement/methods/dream_rsi/README.md) refines a bounded I exploration policy from discovery histories and real holdout confirmation. Policy artifacts enter I identity separately from H execution artifacts. Daily [learning material production](lab/learning/README.md) is configured independently of search. Application triggers processing, Run persists attributed records, and the default method produces pending observations without inferred scores. Core receives no improvement-role or scoring responsibilities.

## State and recovery

| State | Meaning |
|---|---|
| Configuration | Choices for the next session |
| RuntimeManifest | Actual model, normalized mechanism parameters, declared implementation versions, prompt contents, and consumed artifacts |
| Session | Canonical messages, committed context decisions, manifest, and concise run/failure records |
| Live events | Frontend observation; not a complete persisted request trace |

Core enforces per-turn tool allowances and bounds consecutive truncated responses; see [runtime rules](core/README.md#runtime-rules). Provider retries and monetary cost require separate accounting.

Recovery validates recorded contents and required artifacts, then continues with current configuration. Complete environment snapshots are appended in the same Session when they change. It does not restore arbitrary Python objects, snapshot algorithm source, or replay requests with unknown cost. Details belong to [Run](run/README.md#recovery) and [Session](core/session/README.md).

## Choose an extension point

| Need | Guide |
|---|---|
| Change request context | [Context manager](lab/context_manager/README.md) |
| Add model-callable operations | [Tools](lab/tools/README.md) |
| Replace filesystem or shell access | [Environment](lab/environment/README.md) |
| Search text candidates | [Improvement](lab/improvement/README.md) |
| Verify and adopt across generations | [RSI](lab/rsi/README.md) |
| Register and assemble a mechanism | [Catalog](lab/catalog/README.md) |
| Add a frontend | [Interactive](interactive/README.md) |

The [offline extension example](../examples/extensions/README.md) demonstrates registration, assembly, and interaction without model access. [Tests](../tests/README.md) enforce boundaries and covered behavior; [Lab limitations](lab/ALGORITHM_AUDIT.md) describe remaining constraints.

Runtime authorization has a Core contract, a Lab file/execution policy, Interactive confirmation, and Run assembly. Standard Run protects known credential paths and asks for external file access and local code execution. See [Environment permissions](lab/environment/README.md#apply-lightweight-permissions). It does not provide OS isolation or sandbox arbitrary trusted Python plugins.
