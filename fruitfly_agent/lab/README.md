# Lab

[Up: Runtime Architecture](../README.md)

Add tools, execution backends, context strategies, and improvement algorithms through Core's public contracts. Lab owns implementations and registration; Run assembles them and Application manages their lifetime. The independent [Improvement runtime](../improvement/README.md) owns reliable stage orchestration through injected ports.

## Choose a module

| Module | Responsibility |
|---|---|
| [Catalog](catalog/README.md) | Mechanism definitions, parameters, dependencies, and installers |
| [Optimization targets](improvement/targets/README.md) | Explicit owner declarations, text projections and retained-state helpers |
| [Context manager](context_manager/README.md) | Augmentation, externalization, and reduction |
| [Tools](tools/README.md) | Model-callable file, shell, IPython and public web operations |
| [MCP client](mcp/README.md) | Optional selected tools from independently installed local stdio services |
| [Environment](environment/README.md) | Local filesystem and process backend |
| [Base prompt](base_prompt/README.md) | Built-in prompt text and its target adapter |
| [Execution policy](execution_policy/README.md) | Typed execution parameters and the H candidate adapter |
| [Improvement](improvement/README.md) | Component workflow, task evidence, experience and optional verification |
| [RSI](rsi/README.md) | Verified adoption and continuation across generations |
| [Known limitations](ALGORITHM_AUDIT.md) | Current budget, I/O, cancellation, and composition limits |

## Improvement and RSI

| Question | Owner | Example |
|---|---|---|
| What runs, and what can change? | Object module and target adapter | Base prompt or Skill catalog guidance |
| How are improvements proposed and compared? | Improvement | Replaceable generators propose evidence-based component edits. |
| Who verifies, adopts, and continues? | Human or explicit RSI host | Review one result, or run verified text evolution. |

Improvement runs independently of RSI. Its public stage contracts separate proposal, execution, composition, output selection, verification and reflection. Persistent RSI requires an explicit host and verification policy; only confirmed activation advances the deployed version.

Generators implement `CandidateGenerator`; `WorkflowBindings` injects replaceable stages. Existing H/S text owners reuse the same execution and adoption path. I edits use the registered fixed-depth editor-comparison runner and independent paired verification.
See [editor experiments](improvement/improver/README.md).

Task-local work can use execution evidence without answers or scores. Persistent candidates require independent verification before human adoption. Attributed experience is staged separately at task boundaries and enters the library only after explicit review.

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
| Dependencies | Import only Core, the shared Runtime specification and Lab; inject model, filesystem, network, and host capabilities. |
| Input ownership | Treat context frames and nested messages as read-only; return new projections or decisions. |
| State | Specify request, run, Session, or workspace scope; define reset and recovery behavior. |
| Budgets | State which calls, bytes, tokens, time, and queue waits are actually bounded. |
| Failure | Preserve protocol distinctions between no-op, ordinary failure, and cancellation. |
| Resources | Register owned resources during construction; clean up failed assembly and cancellation. |
| Registration | Declare parameters, contributions, dependencies, implementation identity, external effects, a concise distinguishing description, and implementation/guide paths. Mark necessary user inputs explicitly; keep tuning in YAML. |
| Selectable implementations | Place each method in its owner's `methods/<method_name>/`; keep shared contracts, services and module registration outside that directory. |
| Improvement readiness | Design meaningful editable content before implementation; provide the owner registration entry and demonstrate a candidate changes isolated execution. See [Design for Improvement](#design-for-improvement). |
| Verification | Observe useful output, disabled behavior, failure, cancellation, isolation, and recovery where applicable. |

Catalog checks declared parameters, dependencies, conflicts, stage shape, and returned assembly state. It does not prove deep immutability, resource budgets, algorithm quality, or every mechanism combination. Plain interface conformance is insufficient.

## Design for Improvement

FruitFlyAgent is designed for RSI. Every new selectable algorithm must expose at
least one meaningful optimization surface from its initial design. Prompts,
parameters, policy choices and explicitly retained content are possible surfaces.
An unused setting or a configurable value that never reaches candidate execution
does not satisfy this requirement. Do not invent tunable switches for immutable
protocol, authorization or integrity rules.

Major feature modules provide an owner-controlled Improvement registration entry,
normally `improvement.py`. Method declarations feed that entry and the existing
[Catalog configuration](catalog/CONFIGURATION.md#declare-editing-separately),
target adapters and execution contracts. Reuse an existing equivalent public
entry where appropriate; do not create another discovery registry or model loop.
Algorithm execution consumes validated values and injected capabilities without
importing an editor, search controller or Application.

| Design decision | Required declaration and evidence |
|---|---|
| Ownership | H/S/I role, stable component identity and effective content identity |
| Mutable content | Prompt text, parameters or policy fields; defaults, types and bounds |
| Protected content | Fixed invariants, model/credential bindings and outer allowances |
| Candidate lifecycle | Grant, validate, materialize, execute, verify and activate through existing public contracts |
| State | Initial content, update/reset rules, trial isolation and recovery dependencies |
| Runtime effects | Changed content observed in actual supported candidate execution |
| Unsupported backend | Explicit admission failure before model work; no silent use of baseline behavior |

Place a concrete selectable implementation in `methods/<method_name>/` under the
closest owning module. Keep shared protocols, storage/retrieval capabilities,
validation and module registration outside `methods/`. Method-specific prompts,
configuration and declarations remain with that method. Add an independent README
when the method forms a module. Methods may depend on owner public contracts;
they must not import sibling implementations to obtain hidden shared behavior.
The owning composition entry registers methods explicitly.

A task-local working memory is execution state, not an automatic S update. The
policy and prompt that maintain it belong to H when they control ordinary task
execution. Editing the Improvement procedure itself belongs to I.

## Test and evaluate

```bash
.venv/bin/python -m tests --area lab --area workflows
.venv/bin/python -m unittest discover -s tests -t .
```

| Evidence | Scope |
|---|---|
| Offline regression | Public behavior, assembly, Application use, and resource handling |
| Live model checks | Actual model behavior; explicit network and cost authorization required |

Researchers manage formal experiments and their records externally. Learning mechanisms still define initial state, data splits, reset rules, and state sharing. A RuntimeManifest is not a source or learning-state snapshot. [Eval](../../fruitfly_eval/README.md) can consume public capabilities, but must not define their production interfaces.

Lab has no shared environment variables and does not read ambient API keys. Hosts inject credentials required by selected tools. [Configuration](../../CONFIGURATION.md) selects mechanisms; each child guide describes its own external effects.


Shared model role invocation: [Agent runner](agents/README.md).
