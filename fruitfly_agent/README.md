# Runtime Architecture

[Up: FruitFlyAgent](../README.md)

FruitFlyAgent separates the Agent loop, model adapters, Application lifecycle, and replaceable algorithms. Run assembles them into an interactive runtime.

## Modules

| Module | Owns | Depends on |
|---|---|---|
| [Core](core/README.md) | Messages, loop, tools, context contracts, and Session persistence | Core only |
| [Providers](providers/README.md) | Model API requests, streaming, and error mapping | Core and Providers |
| [Interactive](interactive/README.md) | Application lifecycle, multi-turn state, events, and terminal | Core and Interactive |
| [Lab](lab/README.md) | Tools, environments, context strategies, optimization, and RSI | Core and Lab |
| [Run](run/README.md) | Configuration, Provider construction, assembly, and CLI | All runtime layers |
| [Eval](../eval/README.md) | Optional benchmark conditions, runners, and reports | Core, Providers, Lab, and Eval |

Eval consumes public runtime capabilities. Removing it must leave normal Agent use and algorithm development intact.

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

## State and recovery

| State | Meaning |
|---|---|
| Configuration | Choices for the next session |
| RuntimeManifest | Actual model, normalized mechanism parameters, declared implementation versions, prompt contents, and consumed artifacts |
| Session | Canonical messages, committed context decisions, manifest, and concise run/failure records |
| Live events | Frontend observation; not a complete persisted request trace |

Core enforces per-turn tool allowances and bounds consecutive truncated responses; see [runtime rules](core/README.md#runtime-rules). Provider retries and monetary cost require separate accounting.

Recovery checks artifact contents and the full manifest. It does not restore arbitrary Python objects, snapshot algorithm source, or replay requests with unknown cost. Details belong to [Run](run/README.md#recovery) and [Session](core/session/README.md).

## Choose an extension point

| Need | Guide |
|---|---|
| Change request context | [Context manager](lab/context_manager/README.md) |
| Add model-callable operations | [Tools](lab/tools/README.md) |
| Replace filesystem or shell access | [Environment](lab/environment/README.md) |
| Search text candidates | [Optimization](lab/optimization/README.md) |
| Verify and adopt across generations | [RSI](lab/rsi/README.md) |
| Register and assemble a mechanism | [Catalog](lab/catalog/README.md) |
| Add a frontend | [Interactive](interactive/README.md) |

The [offline extension example](../examples/extensions/README.md) demonstrates registration, assembly, and interaction without model access. [Tests](../tests/README.md) enforce boundaries and covered behavior; [Lab limitations](lab/ALGORITHM_AUDIT.md) describe remaining constraints.
