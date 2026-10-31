# Run Improvement Stages

[Up: Improvement Runtime](../README.md)

`WorkflowServices` supplies cancellation, resource ownership, durable events,
observational usage and independent stage times. It constructs no Provider or
concrete editor/evaluator.

| Stage | Default seconds | Scope |
|---|---:|---|
| Editor | 1200 | One editing invocation, including repair |
| Execution | 3600 | One leaf task execution |
| Evaluator | 1200 | One assessment or comparison |

Time starts when work begins. Same-stage nested work shares its invocation time;
subsequent stages receive their full independent time. Composite task batches
and fixed-I studies schedule leaf invocations rather than impose a shared deadline.
User cancellation propagates globally. Timeout retires local work and preserves
completed records. Unconfirmed cleanup prevents further scheduling.

Usage observations never authorize or reject work. There are no root allocations,
child quotas or protected finalization reserves. Search schedules and explicit
stop policies determine when another round starts.

| File | Responsibility |
|---|---|
| `timing.py` | Invocation clocks and stage roles |
| `services.py` | Injected operations, observations and cleanup |
| `operations.py` | Stage result validation and attributable failure |
| `controller.py`, `engine.py` | Shared search transitions and result retention |
| `problems.py`, `state.py` | Injected search callbacks and local state |

Offline checks: `tests.improvement.test_stage_timing`,
`tests.improvement.test_services`, `tests.improvement.test_reliability`.
