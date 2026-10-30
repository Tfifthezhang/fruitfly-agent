# Runtime Architecture

[Up: FruitFlyAgent](../README.md)

FruitFlyAgent separates the Agent loop, model adapters, Application lifecycle, and replaceable algorithms. Run assembles them into an interactive runtime.

System configuration selects H/S/I component documents through one shared
[runtime specification](runtime_spec/COMPONENTS.md). Daily config, experiment
baseline and generated candidate use the same loader/projection and runtime
assembly. [Catalog declarations](lab/catalog/CONFIGURATION.md) own supported
fields and adapters; [experiment grants](experiments/CONFIGURATION.md) authorize
bounded changes. See the [configuration navigation tree](../CONFIGURATION.md#navigate-the-configuration-tree).

## Modules

| Module | Owns | Depends on |
|---|---|---|
| [Runtime specification](runtime_spec/README.md) | Serializable harness profiles and execution parameters | Core and basic serialization only |
| [Core](core/README.md) | Messages, loop, tools, context contracts, and Session persistence | Core only |
| [Providers](providers/README.md) | Model API requests, streaming, and error mapping | Core and Providers |
| [Interactive](interactive/README.md) | Application lifecycle, multi-turn state, events, and terminal | Core and Interactive |
| [Improvement](improvement/README.md) | Reliable stage execution, budgets, receipts and stopping through injected ports | Core and Improvement |
| [RSI runtime](rsi/README.md) | Reliable generation transitions and activation reconciliation through injected hosts | Core, Improvement and RSI |
| [Developer Extensions](extensions/README.md) | Developer registration over public owning contracts | Core, Improvement, Lab and Interactive |
| [Lab](lab/README.md) | Tools, environments, context strategies, improvement implementations, and RSI experiment defaults | Core, Runtime specification, Improvement and Lab |
| [Run](run/README.md) | Configuration, Provider construction, assembly, and CLI | All runtime layers |
| [Eval](../eval/README.md) | Optional single-configuration benchmark execution and reports | Core, Runtime specification, Improvement, Providers, Lab, and Eval |
| [Experiments](experiments/README.md) | Independent CLI, file defaults and public service composition | Run, Lab, Providers, Interactive and optional Eval; no reverse imports |

Eval prepares and mounts a Linux Agent runtime, launches the native CLI inside
Harbor task environments, then collects official verifier results. Shared
preparation and lifecycle stay in Eval; benchmark declarations do not configure
runtime interfaces. Shared and independent verifiers reuse the same Harbor
integration; only Agent environments receive the Agent runtime and credentials.
Removing Eval leaves normal Agent use and generic improvement intact.

The [Improvement runtime](improvement/README.md), with [Lab implementations](lab/improvement/README.md), separates candidate generation, execution, composition, selection, verification and reflection through public ports. Object-owned component adapters expose legal changes; Run and Application retain persistence and activation.

[Instruction components](lab/improvement/targets/README.md#improve-multiple-instruction-components) retain separate H/S/I ownership. A candidate can modify multiple executable components; unregistered bindings and missing runner capabilities fail explicitly.

Lab registrations own mechanism metadata. Improvement menus use generator, component, source and allocation contracts. Adding a generator does not add algorithm-specific branches to Run or the terminal.

New selectable algorithms must be designed for Improvement from the start, with
meaningful editable content and evidence that candidates affect actual execution.
Major feature modules own their Improvement registration entry. Concrete methods
belong in the owning module's `methods/`; shared contracts and services remain
outside. See [Lab design rules](lab/README.md#design-for-improvement).

[Execution workflows](lab/workflow/README.md) own bounded H execution. Retained Skill and memory documents belong to S. I editor instructions use a registered [fixed-depth comparison](lab/improvement/improver/README.md)
that measures the downstream H/S changes produced by each editor.

Task materials and executions need no score. Persistent publication requires an injected verification policy; current-task selection retains its weaker assurance. The experience library is a separate attributed S update after explicit pending-lesson review.
Search preserves reference results, separates stopping from assurance, and charges nested
work to one root budget. No component changes during a task execution.

Hosted executions expose immutable terminal facts through the common
[execution contract](lab/improvement/execution/README.md#record-execution-facts).
Optional completed-process assessment supplies feedback and can guide a separate
next editing seed. Official selection and independent adoption retain their own
rules; generic files and container benchmarks use the same contracts.

Run separates [configuration](run/configuration/README.md), [runtime preparation](run/runtime/README.md), [storage](run/storage/README.md), [improvement hosting](run/improvement/README.md), and [adapters](run/adapters/README.md). Its Factory composes these services; leaf services receive explicit capabilities and own their local state.

Interactive separates Contracts, Application, Session, Interaction, and Terminal. It keeps lifecycle authority in Application and exposes independent search, candidate, and task material contracts. Its terminal uses [registered command handlers](interactive/terminal/README.md#register-a-command); feature flows consume explicit capabilities and share one input owner.

Built-in chat appends completed output to native terminal scrollback; menus borrow
an alternate screen. Lab publishes execution descriptions through Catalog, and
Run projects them into Interactive status separately from the local workspace.
Welcome, `/lab` and `/status` describe the activated environment without backend
inspection in the terminal.

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

User attachments and image tool results share Core image blocks. Providers encode
them for the chosen protocol, including attributed Chat image observations after
the complete tool-result batch. Run freezes local attachments and retains granted
media resources; file tools use the selected local or SSH environment. See
[image submission](run/README.md#submit-images). Audio/video input, native media
output generation and realtime media are not implemented.

Task packages are explicit inputs. Hosts can save human corrections through the [task-material API](lab/improvement/tasks/README.md#maintain-training-acceptance). Ordinary conversations do not create training material. Improvement lessons enter S only after explicit review; Core owns neither scoring nor adoption.

[Web tools](lab/tools/web/README.md#extend-and-verify-offline) consume separate
search and fetch service contracts. Lab owns vendor adapters and service factories;
Catalog declares credential dependencies. Configuration and Eval consume those
declarations without vendor-specific branches. Model Providers remain independent.

## State and recovery

| State | Meaning |
|---|---|
| Configuration | Saved choices; explicitly applied through Application or used on start/recovery |
| RuntimeManifest | Actual model, normalized mechanism parameters, declared implementation versions, prompt contents, and consumed artifacts |
| Session | Canonical messages, committed context decisions, manifest, and concise run/failure records |
| Live events | Frontend observation; not a complete persisted request trace |

Core enforces per-turn tool allowances and bounds consecutive truncated responses;
Run and Eval share the declarative execution configuration (tool limit default 64).
Manifest schema 7 records effective execution parameters and the resolved harness
inventory. Historical manifests remain validated against their original contents. Terminal loop diagnostics distinguish
budget stops from normal completion without granting task success. See
[runtime rules](core/README.md#runtime-rules). Provider retries and monetary cost
require separate accounting.

Recovery validates recorded contents and required artifacts, then continues with current configuration. Complete environment snapshots are appended in the same Session when they change. It does not restore arbitrary Python objects, snapshot algorithm source, or replay requests with unknown cost. Details belong to [Run](run/README.md#recovery) and [Session](core/session/README.md).

## Choose an extension point

| Need | Guide |
|---|---|
| Change request context | [Context manager](lab/context_manager/README.md) |
| Add model-callable operations | [Tools](lab/tools/README.md) |
| Connect independently installed MCP tools | [MCP client](lab/mcp/README.md) |
| Replace filesystem or shell access | [Environment](lab/environment/README.md) |
| Execute on an external SSH server | [SSH environment](lab/environment/ssh/README.md) |
| Search text candidates | [Improvement](lab/improvement/README.md) |
| Optimize a shared candidate across tasks | [Task sets](lab/improvement/task_sets/README.md) |
| Verify and adopt across generations | [RSI runtime](rsi/README.md) |
| Load developer extensions | [Developer Extensions](extensions/README.md) |
| Register and assemble a mechanism | [Catalog](lab/catalog/README.md) |
| Add a frontend | [Interactive](interactive/README.md) |

The [offline extension example](../examples/extensions/README.md) demonstrates registration, assembly, and interaction without model access. [Tests](../tests/README.md) enforce boundaries and covered behavior; [Lab limitations](lab/ALGORITHM_AUDIT.md) describe remaining constraints.

Runtime authorization has a Core contract, a Lab file/execution policy, Interactive confirmation, and Run assembly. Standard Run protects known credential paths and asks for external file access and local code execution. See [Environment permissions](lab/environment/README.md#apply-lightweight-permissions). It does not provide OS isolation or sandbox arbitrary trusted Python plugins.

Optional external tool providers use Catalog's asynchronous preparation contract
before synchronous assembly. Lab owns transport and exact schemas; Run supplies
startup approval, ownership and artifacts; Interactive exposes generic tool-service
status and separate call authorization. The [MCP client](lab/mcp/README.md) supports
local stdio, including alongside SSH execution. Its frozen declaration artifacts
enter manifest schema 8; ordinary runtimes retain schema 7.

Run's configuration menu restores default harness settings through its ordinary
save/discard flow while preserving daily model selections. Eval consumes the
independent default profile, freezes runtime inputs and explicitly selects an
unrestricted host strategy inside task containers. Benchmark adapters do not
define runtime configuration fields; tools and Core share one execution path.

## Separate search, evolution and evaluation

Improvement searches and compares candidate changes. RSI adopts eligible versions
and binds their H/S/I in later generations. Eval executes a fixed Agent on external
benchmarks and can optionally register a runner/official-assessment adapter.
Normal Improvement/RSI remain usable without Eval; `eval run` does not evolve.

Editing, [assessment](lab/improvement/assessment/README.md), execution and
[termination](lab/improvement/termination/README.md) have separate owners. Online
assessment consumes immutable event positions. Feedback/control is explicit;
version switching requires an implemented backend boundary. Current managed
handles support scoped stop; live code/state replacement is not implied.

The Improvement [extension contract](improvement/extensions/README.md) supplies
immutable lifecycle snapshots and bounded proposal context. Research state,
progress analysis, soft reserves and task-output validation remain
[replaceable Lab mechanisms](lab/improvement/research/README.md). They share
ordinary and candidate configuration paths without adding a second Agent loop.

Request measurement is a separate Lab capability from reduction. Core's generic
measurement/commit contracts validate final projections, while Lab owns heuristic
calibration, continuity summaries and incremental working memory. Concrete
methods and editable prompts live under [reduction methods](lab/context_manager/reduction/README.md);
shared evidence retrieval remains outside them. Measurement reports precision
and uncertainty rather than presenting all counts as exact. See
[request budgets](lab/context_manager/measurement/README.md).

Agent, Improvement and RSI retain separate state machines. Core's bounded
operation supervisor provides shared cooperative timeout/cancellation behavior;
search decisions stay in Lab. Optimization representation, update timing,
activation boundary and state scope use the [optimization contract](improvement/contracts/README.md#declare-optimization-surfaces).
