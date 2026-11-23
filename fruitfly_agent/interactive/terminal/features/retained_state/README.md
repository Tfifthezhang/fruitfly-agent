# Inspect retained state

[Up: Terminal Features](../README.md)

[commands.py](commands.py) registers `/memory` and `/skills` using injected public
Application callbacks. [views.py](views.py) renders retained entries and status, pending batch
IDs, source counters and maintenance errors. `/memory` shows the storage location,
automatic upkeep state, trigger state and next command. `/memory details` shows
retained documents and counters. `/skills` shows only its documents and pending updates;
memory counters and maintenance failures are excluded. Inspection makes no model calls.

Automatic upkeep runs after configured evidence thresholds at idle boundaries.
`/memory run` explicitly requests owner-validated upkeep even below those thresholds.
`/memory run OPERATION` resumes one named, already authorized batch.
Both paths use the same durable batch journal, model activity stream and atomic publish.

Use `read ID` for a retained document, or `commit UPDATE` / `reject UPDATE` for a
pending batch. Application guards writes while busy. Commit refreshes the runtime
with the same conversation. Human review expresses adoption, not independent
quality verification. These commands do not install external packages.

`/memory retry OPERATION` explicitly authorizes retrying an unknown call outcome and
immediately resumes that exact batch. Any model activity is shown in the interactive
stream. Repeating the command for an already authorized batch is safe and continues
the same recovery path. New input alone cannot authorize replay. Unresolved batches
block automatic upkeep and appear in `/memory`; use `/memory run OPERATION` to resume an already
authorized batch or `/memory retry OPERATION` when authorization is still required.

Validated automatic memory maintenance publishes without a pending review. The
view reports saved and loaded revisions, refresh errors and unresolved operations.
A failed refresh keeps the previous snapshot available for the task.
`/memory import WORKSPACE` explicitly imports validated legacy project memory and
evidence into the user store without a model call. Unknown calls retain their
identity and require separate retry authorization.

`/memory discard OPERATION` releases an inactive known batch after a configuration
or base-revision conflict. It can also end an authorized legacy batch that predates
recovery journals. Responses remain inspectable and evidence cursors remain unchanged;
ending a legacy batch does not delete source evidence. A batch with an unknown outcome
still needs explicit retry authorization before it can be discarded.
Runtime replacement and shutdown give maintenance a bounded grace period before
cancelling it. Foreground input defers refresh while maintenance is running.
