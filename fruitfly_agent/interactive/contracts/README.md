# Interaction Contracts

[Up: Interactive](../README.md)

Define the data and capabilities shared by hosts, Application, Session, and frontends. This package contains protocols and immutable views; it does not construct Providers, manage resources, or implement algorithms.

| File | Public entries / responsibility |
|---|---|
| [runtime.py](runtime.py) | RuntimeFactory, RuntimeSession, RuntimeAuthorization, and the RuntimeHandle protocol |
| [commands.py](commands.py) | InteractiveCommand, CommandResult, optional read-only CommandPanel/CommandSection, CommandContext, and CommandHandler |
| [events.py](events.py), [models.py](models.py) | Event envelopes, EventSink, status, history, and session views |
| [configuration.py](configuration.py), [model_setup.py](model_setup.py) | Configuration choices, optional default-restoration capability, model forms and staging |
| [mechanism_setup.py](mechanism_setup.py) | Optional guided mechanism forms, non-secret credential status and atomic staging |
| [improvement.py](improvement.py) | Component workflow choices and parameters, preview/execution, activity, progress, optional history/log queries and submission receipts |
| [experience.py](experience.py) | Independent pending-lesson views and explicit commit/reject capability |
| [candidates.py](candidates.py) | Candidate views with evidence assessments, review, and isolated preparation/activation contracts |
| [task_packs.py](task_packs.py) | Task material and correction views/services |

Implement only the capabilities a host supplies. Optional `ImprovementSubmissionService` records authorized intent before the Application task is scheduled, including immediate cancellation; it grants no execution or activation authority. `ComponentImprovementClient` supplies typed workflow configuration and preview. Stage protocols replace algorithm-specific search signatures. Improvement, candidates, and task materials are independently injected. Candidate preparation returns a handle satisfying this package's RuntimeHandle protocol. The concrete constructor belongs to [Application](../application/README.md) and is exported as `fruitfly_agent.interactive.RuntimeHandle`.

Runtime protocols reference public Core result, context-item, and permission types. Other view contracts remain independent of Core. Contracts do not import any Interactive implementation, including in TYPE_CHECKING blocks. Event and data serialization behavior is independent of directory layout; no schema or project version changes.

`InteractiveStatus.mechanism_details` describes visible active components, including
capability-only tools and execution environments. `InteractiveMechanism.tool_names`
contains declared tool names; the status's `tool_names` identifies installed tools.
The separate `mechanisms` tuple retains the experimental-mechanism ID collection.
Application sets `improvement_available` when its injected service implements the
component-workflow client protocol, without querying or constructing that service.
Availability does not mean an experiment is running.

`CommandResult.panel` optionally carries a `CommandPanel` of titled
`CommandSection` values, each containing a category hint and labelled text rows.
The original `text` field remains a complete plain-text fallback. These frozen
views describe text and category hints rather than terminal styling, service
objects or runtime configuration.
Renderers select layout and color without inspecting a command's name.

For Session-backed runtimes, `InteractiveStatus.message_count` and
`RunStarted.message_count` describe committed canonical conversation messages,
independent of the retained model projection. Metadata and compaction entries do
not count. See [Session integration](../session/README.md) for live counting and
the fallback used by hosts without a Session store.

No environment variables, model calls, filesystem writes, or resource ownership. Concrete effects belong to service implementations. See [Run adapters](../../run/adapters/README.md) and [terminal feature extensions](../terminal/features/README.md).

Configuration mechanism views carry registration-owned implementation/guide paths and `input_parameters`. Workflow views expose available components, generators, execution strategies, materials, verification modes and effect scopes. Parameter views carry descriptions, choices, nullability and numeric bounds. These views describe input; the host validates requests and binds confirmed previews to execution.

```bash
.venv/bin/python -m unittest tests.architecture.test_boundaries tests.contracts.test_public_api tests.contracts.test_signatures -v
.venv/bin/python -m mypy
```

Tool start/finish events carry an optional plain-text `description`. Tool finish
adds `status` (`succeeded`, `failed`, `cancelled`, or `unknown`) and optional
`elapsed_seconds`. These fields are renderer-neutral and additive. Older payloads
without status deserialize as `unknown`; frontends must not infer success from
completion alone. `terminate` requests stopping the loop and is independent of
success/failure. Existing event IDs, sequence ordering and unknown-field handling
remain unchanged.

`WorkflowConfiguration.executions` carries execution labels, compatible component
IDs, material choices, typed parameters and declared defaults. `WorkflowRequest`
adds `execution_id` and `execution_parameters` without changing existing positional
fields. The terminal can select editor comparison without encoding algorithm IDs.
Hosts can omit the new execution views to keep existing custom menus.
