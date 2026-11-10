# Runtime Architecture

[Up: FruitFlyAgent](../README.md)

FruitFlyAgent separates the Agent loop, model adapters, Application lifecycle, and replaceable algorithms. Run assembles them into an interactive runtime.

System configuration selects H/S/I component documents through one shared
[runtime specification](runtime_spec/COMPONENTS.md). Daily config, experiment
baseline and generated candidate use the same loader/projection and runtime
assembly. Every component retains its protected H/S/I role. Registered owner YAML
supplies text and numeric defaults once; ordinary saves preserve references,
while candidate/export materialization freezes complete effective parameters. [Catalog declarations](lab/catalog/CONFIGURATION.md) own supported
fields and adapters; [experiment grants](experiments/CONFIGURATION.md) authorize
bounded changes. See the [configuration navigation tree](../CONFIGURATION.md#navigate-the-configuration-tree).

## Modules

| Module | Owns | Depends on |
|---|---|---|
| [Runtime specification](runtime_spec/README.md) | Serializable harness profiles and execution parameters | Core and basic serialization only |
| [Core](core/README.md) | Messages, loop, tools, context contracts, and Session persistence | Core only |
| [Providers](providers/README.md) | Model API requests, streaming, and error mapping | Core and Providers |
| [Interactive](interactive/README.md) | Application lifecycle, multi-turn state, events, and terminal | Core and Interactive |
| [Improvement](improvement/README.md) | Reliable stage execution, independent stage times, receipts and stopping through injected ports | Core and Improvement |
| [RSI runtime](rsi/README.md) | Reliable generation transitions and activation reconciliation through injected hosts | Core, Improvement and RSI |
| [Developer Extensions](extensions/README.md) | Developer registration over public owning contracts | Core, Improvement, Lab and Interactive |
| [Lab](lab/README.md) | Tools, environments, context strategies, improvement implementations, and RSI experiment defaults | Core, Runtime specification, Improvement and Lab |
| [Run](run/README.md) | Configuration, Provider construction, assembly, and CLI | All runtime layers |
| [Eval](../fruitfly_eval/README.md) | Optional single-configuration benchmark execution and reports | Core, Runtime specification, Improvement, Providers, Lab, and Eval |
| [Experiments](experiments/README.md) | Independent CLI, file defaults and public service composition | Run, Lab, Providers, Interactive and optional Eval; no reverse imports |

Eval prepares and mounts a Linux Agent runtime, launches the native CLI inside
Harbor task environments, then collects official verifier results. Shared
preparation and lifecycle stay in Eval; benchmark declarations do not configure
runtime interfaces. Shared and independent verifiers reuse the same Harbor
integration; only Agent environments receive the Agent runtime and credentials.
Removing Eval leaves normal Agent use and generic Improvement intact.
Improvement task execution then needs an explicitly registered backend; the
framework supplies no local task executor.

The [Improvement runtime](improvement/README.md), with [Lab implementations](lab/improvement/README.md), separates candidate generation, execution, selection, verification and reflection through public ports. Object-owned component adapters expose legal changes; Run and Application retain persistence and activation.

[Instruction components](lab/improvement/targets/README.md#improve-multiple-instruction-components) retain separate H/S/I ownership. A candidate can modify multiple executable components; unregistered bindings and missing runner capabilities fail explicitly.

Lab registrations own mechanism metadata. Improvement menus use generator, component, source and timing contracts. Adding a generator does not add algorithm-specific branches to Run or the terminal.

New selectable algorithms must be designed for Improvement from the start, with
meaningful editable content and evidence that candidates affect actual execution.
Major feature modules own their Improvement registration entry. Concrete methods
belong in the owning module's `methods/`; shared contracts and services remain
outside. See [Lab design rules](lab/README.md#design-for-improvement).

Retained Skill and cross-session memory libraries belong to S. Descriptions and
bodies share the ordinary candidate assembly path; bodies load on demand.
Application owns threshold-maintenance scheduling and explicit batch adoption.
I instruction targets can be proposed explicitly through [independent stages](lab/improvement/DEVELOPER_GUIDE.md); no automatic nested I comparison backend is installed.

Task materials and executions need no score. Persistent publication requires an injected verification policy; current-task selection retains its weaker assurance. The experience library is a separate attributed S update after explicit pending-lesson review.
Research preserves input results and separates continuation from assurance. Editing, execution and evaluation each receive an independent invocation time. Usage is recorded without quotas. No component changes during a task execution.

Hosted executions expose immutable terminal facts through the common
[execution contract](lab/improvement/execution/README.md#record-execution-facts).
A prompt-driven model evaluator supplies dimension judgments, process signals and candidate-hypothesis checks. Its feedback is an optional input to a later explicit proposal or comparison. Official scores remain unchanged; independent adoption retains its own rules.

Run separates [configuration](run/configuration/README.md), [runtime preparation](run/runtime/README.md), [storage](run/storage/README.md), [improvement hosting](run/improvement/README.md), and [adapters](run/adapters/README.md). Its Factory composes these services; leaf services receive explicit capabilities and own their local state.

Interactive separates Contracts, Application, Session, Interaction, and Terminal. It keeps lifecycle authority in Application and exposes independent search, candidate, and task material contracts. Its terminal uses [registered command handlers](interactive/terminal/README.md#register-a-command); feature flows consume explicit capabilities and share one input owner.

Interactive CLI launches first show an offline [startup panel](interactive/terminal/features/startup/README.md).
Configuration uses the same editor as `/config`; only explicit Start constructs
and connects runtime resources. Failed startup returns to the panel after cleanup.
Application remains the resource lifecycle owner.

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
Run and Eval record effective host execution conditions (daily tool limit default 512).
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
| Execute on an external SSH server | [SSH environment](lab/environment/methods/remote/README.md) |
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
[Execution control](lab/improvement/stages/control.py) have separate owners. Online
assessment consumes immutable event positions. Feedback/control is explicit;
version switching requires an implemented backend boundary. Current managed
handles support scoped stop; live code/state replacement is not implied.

The Improvement [extension contract](improvement/extensions/README.md) supplies
immutable lifecycle snapshots and bounded proposal context. Research state,
evidence navigation and task-output validation remain
[Lab responsibilities](lab/improvement/evidence/README.md). They share
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

Default reduction uses [layered compaction](lab/context_manager/reduction/methods/layered_compaction/README.md)
in deterministic mode: old result previews and readable history archives without
auxiliary model requests. Hybrid summarization uses a declared summary role that defaults to executor.
Working memory remains an alternative in the same exclusive reduction slot.
Context preparation publishes passive stage activity to Session and the terminal.

[Core observation](core/observation/README.md) records correlated operation phases,
classified failures and monotonic durations for ordinary interaction and external
consumers. Source owners classify their own errors. Nested/concurrent stage totals
are separate from observed wall time, and unfinished operations remain unknown.

Eval's [evidence post-processing](../fruitfly_eval/README.md#organize-retained-evidence)
materializes the shared Lab evidence layers after execution and through an offline
organization command. Runtime and generic Improvement remain independent of Eval.

Eval emits compact reading materials through its source adapter. Generic Lab
readers enforce cumulative evidence supply and request-space limits; original
supplements require explicit identities. Model organization is optional before
assessment/proposal. Terminal image drafts accept clipboard paste and dropped
paths through the existing single input owner and Application submission.

## Delegate child tasks

[Subagent](lab/agents/subagent/README.md) is a Lab collaboration capability enabled in the installed default profile. Run constructs
independent child runtimes through the shared assembler; Core retains the loop.
A parent submission owns scheduling, attributed results and bounded retirement.
Interactive consumes a read-only monitor; Provider adapters contain no delegation
policy. Children have private Sessions and context state but may share file effects.
The model role defaults to executor inheritance and can select another catalog alias.
