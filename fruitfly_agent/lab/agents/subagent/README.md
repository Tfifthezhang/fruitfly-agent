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

The owner validates strict parameters. Host permissions, model limits and inherited
Core tool allowances still apply. Requests made by auxiliary context components
remain subject to the execution deadline and their own controls. Request counts
and reported usage are observations, not exact monetary billing.

## Call the tools

| Tool | Arguments | Behavior |
|---|---|---|
| `subagent_spawn` | `task`, optional `context` | Returns `agent_id`, `run_id` and queued state immediately |
| `subagent_send` | Both IDs, `mode`, `message` | `steer` supplements queued/running work; `followup` starts another execution after retirement |
| `subagent_wait` | `executions` containing both IDs, optional `mode=all/any`, `timeout_seconds=30` | Waits at most 60 seconds, returning terminal results or actual unfinished states |
| `subagent_status` | Optional IDs; list `offset`, `limit`; detail `output_offset` | Reads status without work or result consumption; pages full result text in 4,000-character blocks |
| `subagent_cancel` | Both IDs | Requests stop and waits for bounded confirmation |

Tasks, context and messages are bounded to 16,000 characters. Schemas reject unknown
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

## Improve instructions

`improvement.py` registers the child instruction and the five independent tool
instructions through ordinary parameter targets and configuration materialization.
The component remains H. Authorized candidates must change actual request content
or tool declarations in an isolated runtime. Model bindings, limits, authorization,
identities, depth, schema and integrity rules are protected. No model quality gain
is established by fake Provider tests.

## Files and offline checks

| File | Responsibility |
|---|---|
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
