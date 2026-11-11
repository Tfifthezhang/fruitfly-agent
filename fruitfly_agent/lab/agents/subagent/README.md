# Delegate Independent Agent Tasks

[Up: Agents](../README.md)

One `subagent` H component supplies five model tools, a bounded delegation service,
independent child Sessions and a read-only monitor. Construction makes no model
request. Explicit execution uses the selected Provider and tools and may incur cost.

## Enable delegation and choose a model

Use the ordinary [component configuration](../../../runtime_spec/COMPONENTS.md).
The installed default profile enables the component. In `/config`, Agent collaboration exposes Subagent
as one switch; individual control tools cannot be selected separately. Save and apply
while idle through the normal runtime replacement path.

Merge the following into an existing profile. `main-model` is a placeholder alias
that must exist in its model catalog. Credentials stay in the secret environment.

```yaml
models:
  catalog: models.yaml
  roles:
    executor: main-model
    subagent: {inherit: executor}
H:
  subagent: {default: true}
```

Set `models.roles.subagent` to another catalog alias to select a different model,
Provider or protocol. The existing model menu edits these bindings. Inheritance is
retained on save, not converted to a pinned copy of the current executor alias.
No endpoint, key, model override or permission override appears in tool arguments.
Unknown aliases and incompatible model capabilities fail before child model work.

| Setting | Default | Meaning |
|---|---|---|
| `max_concurrent` | 2 | Child executions holding active slots |
| `max_agents` | 8 | Child conversations admitted in one parent scope |
| `run_timeout_seconds` | 600 | Per-execution queue, construction and work deadline |
| `max_model_requests` | 64 | Main child loop request limit per execution |
| `retirement_timeout` | 10 | Seconds to confirm owned resource cleanup |

The owner validates strict parameters. Host permissions, model limits and inherited
Core tool allowances still apply. Requests made by auxiliary context components
remain subject to the execution deadline and their own controls. Request counts
and reported usage are observations, not exact monetary billing.

## Configure protocol and result controls

The registered [default document](methods/managed/defaults.yaml) owns every numeric
service, protocol and result default, plus the child and five tool instructions.
Constructors, Catalog descriptors, model tool schemas and actual service calls
consume these values. `configuration.py` validates cross-field constraints;
Python retains hard identity, text and wait bounds. These controls are protected
from Improvement edits even when visible in configuration.

Customize a workspace component document using the ordinary `file` reference:

```yaml
# In the selected system profile:
H:
  subagent:
    file: components/config/default/H/subagent.yaml
```

The following is a valid partial component document. Omitted values resolve from
the owner defaults; frozen exports contain complete effective values.

```yaml
id: subagent
role: H
implementation: subagent
parameters:
  settings:
    max_concurrent: 2
    retirement_timeout: 10
    protocol:
      max_task_characters: 8000
      max_context_characters: 8000
      max_message_characters: 4000
      default_wait_seconds: 10
      max_wait_seconds: 30
    results:
      output_page_characters: 2000
      default_list_entries: 10
      max_list_entries: 25
```

| Group and field | Default | Meaning |
|---|---|---|
| `protocol.max_task_characters` | 16000 | Spawn and followup task length |
| `protocol.max_context_characters` | 16000 | Initial context and accumulated queued context; running pending steering text |
| `protocol.max_message_characters` | 16000 | Individual steering/followup message length |
| `protocol.default_wait_seconds` | 30 | Omitted wait timeout |
| `protocol.max_wait_seconds` | 60 | Maximum accepted wait timeout |
| `results.output_page_characters` | 4000 | Full result output page size |
| `results.summary_characters` | 4000 | Retained index summary size; full output remains in the artifact |
| `results.task_preview_characters` | 400 | Task text preview size |
| `results.summary_preview_characters` | 2000 | Summary preview size |
| `results.max_preview_characters` | 24000 | Serialized aggregate threshold for omitting row previews; identity metadata remains |
| `results.default_list_entries` | 20 | Omitted model status list size |
| `results.max_list_entries` | 50 | Maximum model status list size |

Default wait/list sizes cannot exceed their maxima. Summary previews cannot exceed
the retained summary size. Text controls are positive integers up to 16000;
default waits are finite values in 0..60 seconds and maximum waits are in .01..60 seconds. Result character controls are positive
integers up to 24000 and list sizes up to 50. Queue steering includes its attribution
prefix in the context length check and rejects overflow before durable admission.
The running steering limit counts pending message text. These controls bound
individual material and result exchanges, not total conversation context or billing.
The interactive monitor retains its own fixed display pagination.

## Call the tools

| Tool | Arguments | Behavior |
|---|---|---|
| `subagent_spawn` | `task`, optional `context` | Returns `agent_id`, `run_id` and queued state immediately |
| `subagent_send` | Both IDs, `mode`, `message` | `steer` supplements queued/running work; `followup` starts another execution after retirement |
| `subagent_wait` | `executions` containing both IDs, optional `mode=all/any`, `timeout_seconds=30` | Uses configured default/maximum waits, returning actual execution states |
| `subagent_status` | Optional IDs; list `offset`, `limit`; detail `output_offset` | Reads status without work or result consumption; pages full result text at the configured size |
| `subagent_cancel` | Both IDs | Requests stop and waits for bounded confirmation |

Tasks, context and messages use the configured limits, each at most 16,000 characters. Schemas reject unknown
arguments, invalid identities, invalid modes, null required values and non-finite
waits. Tool descriptions are independent owner resources. Status and result previews
are bounded; long result text is available through `subagent_status` with
`output_offset`, or through the returned read-only resource when `read` is enabled.
Follow `next_output_offset` until null. List pages use `next_offset`.

A wait timeout does not cancel execution. Cancelling a waiter does not cancel the
child. Results can be read repeatedly; a committed `wait` result suppresses the
automatic duplicate parent notification. Delivery acknowledgement occurs at the
next request boundary after the result enters parent history. `status` does not acknowledge delivery.
Acceptance of a steering message does not establish that the model read it.

`agent_id` names a conversation, while `run_id` names one execution. Followup returns
a new execution ID and retains the conversation's committed history. A busy child
rejects followup; stale IDs cannot steer or cancel newer work. One child has one
active execution. There is no implicit queue of followup tasks.

## Restrict inherited components

`settings.inheritance.mode` is `parent` by default. This retains the parent's
assembled components while excluding delegation. Select `explicit` to rebuild a
child from only the enabled parent component IDs listed in
`settings.inheritance.components`. An empty explicit list constructs a child with
no inherited tools or context components. Host Core execution limits and
permission policy remain in force.

```yaml
id: subagent
role: H
implementation: subagent
parameters:
  settings:
    inheritance:
      mode: explicit
      components: [local-env, read-tool]
```

Component IDs come from the same Catalog and selected parent profile. This example
requires both components enabled in the parent. Unknown, absent, disabled,
duplicate or delegation IDs fail before child work. Nonempty lists in `parent`
mode are rejected. A host without explicit-grant support rejects that mode.

The host re-projects selected component documents through the ordinary loader.
Removed owners do not retain their prompts, artifact bindings or context
installers. Selected owners retain their effective parameters. The actual child
manifest records the resulting runtime. Dependencies are validated normally;
select the required environment/context dependencies explicitly.

This is a component subset, not per-task evidence authorization. For example,
`read-tool` still reads the inherited execution workspace under host policy.
This control alone does not provide assigned-artifact grants, read-only file
scope or filesystem isolation. Do not use it as a substitute for research evidence
tools with exact resource grants. All children of this component use its selected
inheritance policy; tool arguments cannot replace it.

## Own the execution scope

The installed service supplies the host's `run_loop` wrapper around the public
Core loop. [Run](../../../run/runtime/README.md) injects that entry into the ordinary
InteractiveSession, including headless CLI submissions. Embeddings consuming a
RuntimeAssembly must use its `run_loop` when supplied, passing its config, messages,
cancellation signal and context pipeline. Raw Core invocations do not open a
managed delegation scope; their delegation calls are rejected.

Each parent submission owns one scope. Child tools exclude the complete delegation
group, so this method supports one level. A child receives explicit task materials,
not the parent's chat. It has an independent Session, hooks, context pipeline,
measurement state and stateful tool instances, assembled from the frozen profile.
Its tools retain host authorization and share the parent's confirmation service.

Children use the same selected execution workspace; they do not receive automatic
filesystem isolation or merging. Coordinate overlapping edits. Local/SSH
permissions are application checks, not an OS sandbox. Child construction rejects
external tool transports that cannot currently be independently inherited; it does
not silently omit their tools. No child memory maintenance or persistent adoption
service is started.

When the parent model stops with children outstanding, the host waits without
holding a child slot, injects attributed derived results, then lets the parent
integrate them. Results are not human authorization or task-quality certificates.
An exhausted parent allowance cannot be reported as successful result collection.

Cancellation, exceptions, parent completion and runtime close retire owned child
resources. A terminal result is published only after the child invocation and its
owned runtime have retired. Noncooperating execution or cleanup poisons the
service and prevents further admission; stopping does not roll back tool effects.

## Inspect executions

`/subagent` lists up to the latest 50 execution records. `/subagent AGENT_ID` shows
its latest execution; append `RUN_ID` for a particular attempt. These commands
work during parent work, make no model requests and consume the public
[monitor contract](../../../interactive/contracts/README.md). Snapshot revisions
allow consumers to detect changes without a second scheduling authority.

Views distinguish queueing, running, cancelling and terminal states. Cleanup is
reported separately. Main-loop requests, tool counts, actual model identity,
reported tokens and bounded results remain attributed to the child. Missing usage
and unfinished elapsed durations remain unknown. No progress percentage is inferred.

## Retain and recover results

The parent Core Session owns validated `subagent` metadata records. Sharing that
writer supports ordinary idle runtime replacement without competing index locks.
Standalone service tests can supply a separately owned index Session.
Child conversations are stored beside the parent under
`PARENT.jsonl.subagents/AGENT_ID/session.jsonl`. Full outputs use the existing
content-addressed artifact store. Child records include the actual runtime manifest.

Results are written before terminal index publication and before notification.
Identity checks bind artifacts to scope, conversation and execution. Recovery
validates existing referenced results and marks unfinished executions interrupted;
it does not restart models, replay messages or repeat uncertain tool effects.
Missing or corrupt required artifacts fail explicitly. Historical results remain
queryable, but a later parent scope cannot continue old child executions.
Cross-file writes do not constitute a crash-atomic transaction.

## Host research investigations

[Improvement research](../../improvement/DEVELOPER_GUIDE.md#delegate-read-only-evidence-investigation)
can explicitly install the same service/tools over a restricted prepared runtime.
Its spawn schema additionally requires `worker` and exact `materials` paths;
ordinary daily spawn arguments remain task/context. Unsupported material grants
are rejected by hosts without an admission capability.

`settings.research.tools` is a distinct subset of catalog/search/read. The owner
requires `resources: assigned`, `writes: deny` and
`conversation: explicit_materials`. These visible invariant fields reject broader
values. `instructions.evidence_parent` and `instructions.evidence_child` describe
the protocol. These research bridge fields are configurable by users but remain
protected from ordinary task candidate grants: ordinary task execution does not
consume them. Existing child/control instructions retain their admitted edit
surface; I role instructions own research strategy. Resource policy, model
bindings and limits remain protected. The read-only host does not inherit
daily tools or state based on `settings.inheritance`.

A followup retains the original worker/material grant. Admission is checked before
scheduling and snapshots source identities. Validated worker submission can finish
through a terminal tool; ordinary uncontrolled tool termination remains a failed
execution. Invalid worker output is recorded as failed and supplies no citations.

## Improve instructions

`improvement.py` registers the ordinary child and five independent tool
instructions through ordinary parameter targets and configuration materialization.
The component remains H. Authorized candidates must change actual request content
or tool declarations in an isolated runtime. Model bindings, limits, authorization,
identities, depth, schema and integrity rules are protected. No model quality gain
is established by fake Provider tests.

## Files and offline checks

| File | Responsibility |
|---|---|
| `configuration.py` | Typed protocol/result controls and owner default loading |
| `contracts.py` | Identity, task and child factory protocols |
| `execution.py` | Independent Core invocation and steering input |
| `service.py` | Scope, scheduling, result delivery and retirement |
| `storage.py` | Validated indexes and identity-bound artifacts |
| `tools.py`, `views.py` | Five schemas, validation and shared bounded result previews |
| `registration.py`, `improvement.py` | One configuration owner and legal instruction candidates |
| `methods/managed/algorithm.py`, `defaults.yaml` | Concrete installer and executable defaults |

```bash
.venv/bin/python -m unittest tests.lab.test_subagent_service tests.lab.test_subagent_execution tests.lab.test_subagent_tools tests.run.test_subagents tests.interactive.test_subagents
```

These checks use temporary state and fake Providers. See
[Tests](../../../../tests/README.md) for full offline validation.

Enabled Subagent instruction surfaces enter the default Improvement scope. The parent
model can delegate without a separate human request by calling the registered tools.
The runtime does not invent tasks or launch children without a model tool call.

## Configure named research workers

`settings.workers` is one owner-validated YAML mapping. Installed definitions are
`evidence-reader`, `record-organizer`, `cross-record-reader` and
`counterexample-reader`. They select reading strategies, not separate schedulers.
Copy a full definition from [defaults](methods/managed/defaults.yaml) into a workspace
component to customize or add a stable worker name. Each definition requires:

| Field | Runtime effect |
|---|---|
| `description`, `instructions` | Spawn menu guidance and actual child instructions |
| `model_role` | Registered `models.roles` binding, or executor; no inline model alias |
| `capabilities.tools` | Subset of catalog/search/read, intersected with global research tools |
| `capabilities.resources/writes/delegation` | Fixed assigned/deny/disabled authority |
| `inheritance.conversation/state` | Fixed explicit_materials/independent isolation |
| `limits.seconds/model_requests` | Intersected with service and stage execution controls |
| `limits.evidence_characters/evidence_responses` | Local supply intersected with shared stage supply |
| `result.contract/max_characters` | Validated evidence_findings and bounded final output |

Every worker has all fields; unknown fields fail. Stage `delegation.workers` lists
allowed names. The model selects one name and exact materials in its tool call;
arguments cannot broaden the configured authority. Actual worker, model, tools and
effective limits enter the child manifest. Worker definitions remain protected
from ordinary task candidate edits. Ordinary daily spawn retains its existing
interface and inheritance policy; named workers belong to the research host.

