# Improvement Lifecycle Hooks

[Up: Improvement Runtime](../README.md)

`HookRegistry` installs job-local callbacks around the existing edit/execute loop.
It does not create messages, tools, Providers or another model interaction loop.
Lab assembles concrete mechanisms; Run owns durable records and activation.

| Event | Committed observation |
|---|---|
| `before_run` | Admitted baseline before reference execution |
| `before_proposal` | Editing seed before invoking the generator |
| `after_candidate_validated` | Validated candidate identity and attributed reasons |
| `before_trial` | Declared harness before execution |
| `after_trial` | Completed development receipt; private selection trials are excluded |
| `after_round` | Completed round and current incumbent identity when available |
| `before_finalization` | Search has stopped; prepare final selection/verification |
| `before_run_end` | Normal outcome, including refused verification; not a promise after cancellation or fatal integrity failure |

`LifecycleEvent` is frozen and contains a canonical JSON snapshot, never mutable
workflow state. Each callback receives its own copy. Stable priority order applies
within active and observer groups; active handlers run first. Only `before_proposal`
accepts active handlers. They return `ContextContribution` containing at most 32
distinct input artifact references in total. Existing editor read grants expose
them under `context/extensions/`. Hooks cannot return scores, activation decisions,
replacement candidates or changed phase times.

Synchronous invocation, awaiting, timeout and return validation share the stage
boundary. Optional callback failures, conflicting contributions and invalid return
types are journaled and isolated. Required failures stop search; cancellation,
persistence, integrity and cleanup errors propagate. Nested handlers share
the current invocation deadline and must cooperate with cancellation. A trusted Python
extension can retain external references; these contracts are not an OS sandbox.

Embeddings register directly on `WorkflowServices.hooks`. Hosted jobs may supply
`WorkflowBindings.hooks(context)` to install callbacks per job and inner I trial.
The factory must declare a JSON `configuration` dictionary (empty for a stateless
factory); its implementation identity and parameters join frozen previews.
It must register owned
resources immediately. No callback state is shared automatically across jobs.

Offline checks: `tests.lab.test_improvement_mechanisms` and
`tests.architecture.test_improvement_boundaries`.
