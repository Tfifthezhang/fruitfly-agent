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

Eval prepares and mounts a Linux Agent runtime, launches the native CLI inside
Harbor task environments, then collects official verifier results. Shared
preparation and lifecycle stay in Eval; benchmark declarations do not configure
runtime interfaces. Removing Eval leaves normal Agent use and generic improvement intact.

The [Improvement workflow](lab/improvement/README.md) separates candidate generation, execution, composition, selection, verification and reflection through public ports. Object-owned component adapters expose legal changes; Run and Application retain persistence and activation.

[Instruction components](lab/algorithms/README.md#improve-multiple-instruction-components) retain separate H/S/I ownership. A candidate can modify multiple executable components; unregistered bindings and missing runner capabilities fail explicitly.

Lab registrations own mechanism metadata. Improvement menus use generator, component, source and allocation contracts. Adding a generator does not add algorithm-specific branches to Run or the terminal.

[Execution workflows](lab/workflow/README.md) own bounded H execution. Retained Skill and memory documents belong to S. I editor instructions use a registered [fixed-depth comparison](lab/improvement/improver/README.md)
that measures the downstream H/S changes produced by each editor.

Task materials and executions need no score. Persistent publication requires an injected verification policy; current-task selection retains its weaker assurance. The experience library is a separate attributed S update after explicit pending-lesson review.
Search preserves reference results, separates stopping from assurance, and charges nested
work to one root budget. No component changes during a task execution.

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

Daily [learning material production](lab/learning/README.md) is configured independently of improvement. Application triggers processing and Run persists attributed observations. Core has no scoring or adoption responsibility.

[Web tools](lab/tools/web/README.md#extend-and-verify-offline) consume separate
search and fetch service contracts. Lab owns vendor adapters and service factories;
Catalog declares credential dependencies. Configuration and Eval consume those
declarations without vendor-specific branches. Model Providers remain independent.

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
| Execute on an external SSH server | [SSH environment](lab/environment/ssh/README.md) |
| Search text candidates | [Improvement](lab/improvement/README.md) |
| Verify and adopt across generations | [RSI](lab/rsi/README.md) |
| Register and assemble a mechanism | [Catalog](lab/catalog/README.md) |
| Add a frontend | [Interactive](interactive/README.md) |

The [offline extension example](../examples/extensions/README.md) demonstrates registration, assembly, and interaction without model access. [Tests](../tests/README.md) enforce boundaries and covered behavior; [Lab limitations](lab/ALGORITHM_AUDIT.md) describe remaining constraints.

Runtime authorization has a Core contract, a Lab file/execution policy, Interactive confirmation, and Run assembly. Standard Run protects known credential paths and asks for external file access and local code execution. See [Environment permissions](lab/environment/README.md#apply-lightweight-permissions). It does not provide OS isolation or sandbox arbitrary trusted Python plugins.

Run's configuration menu restores default harness settings through its ordinary
save/discard flow while preserving daily model selections. Eval consumes the
independent default profile, freezes runtime inputs and explicitly selects an
unrestricted host strategy inside task containers. Benchmark adapters do not
define runtime configuration fields; tools and Core share one execution path.
