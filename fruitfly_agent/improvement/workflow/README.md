# Workflow Kernel

[Up: Improvement Runtime](../README.md)

`engine.py` implements shared round transitions through `SearchProblem` callbacks.
`controller.py` binds single-task ports and validates parent, component, task,
state, conditions and result identities. Concrete batch search operations and
strategy registration belong to [Lab](../../lab/improvement/workflow/README.md).

`state.py` owns one job-local transition state. It is not passed to extensions.
`operations.py` covers deferred synchronous invocation, awaiting and result
validation, then normalizes stage-local failures while preserving cancellation,
root deadlines and integrity errors. Failures never grant assurance. Earlier
completed executions remain available after generation, execution, measurement
or selection failure. Verification failure removes publication eligibility.

`services.py` supplies restricted generator capabilities, operation deadlines,
owned resource retirement and journal delivery. Journal failure is fatal. On
cancellation an operation waits at most ten seconds for retirement; unconfirmed
work stops scheduling. Each resource close also has a ten-second bound; all closes
are attempted before a cleanup error is raised. Hosts must supply durable sinks.

`budget.py` reserves before work. Child allocations hold quota and leaf work
charges ancestors once. Closing returns unused quota. Confirmed external work can
settle after cancellation; unknown usage consumes its reserved maximum. Root and
local deadlines remain distinct. Final selection and verification use protected
allocations. Tokens, monetary cost and SDK retries require separate accounting.

Concrete [selection](../../lab/improvement/assessment/README.md),
[exploration](../../lab/improvement/strategies/README.md) and
[soft stopping](../../lab/improvement/termination/README.md) belong to Lab.
The engine executes injected operations; it does not decide their algorithms.
Managed problems apply deadlines at leaf stages, allowing composite operations
to retire a timed-out leaf and persist its receipt before proceeding. Custom
problems receive the normal operation deadline unless explicitly managed.
No workflow resource changes production configuration or replays uncertain work.

The resident event tail has 256 entries; the injected sink receives every event.
Unknown external usage has a separate cumulative counter and is not lost when the
tail rotates. Closed child budgets are removed from the parent's live resources.
See [lifecycle hooks](../extensions/README.md) for extension and failure boundaries.

Offline checks: `tests.lab.test_improvement_reliability`,
`tests.lab.test_improver`, `tests.lab.test_task_set_lifecycle`.
