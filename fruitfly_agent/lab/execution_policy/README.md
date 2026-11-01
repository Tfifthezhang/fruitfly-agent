# Configure Execution Policy

[Up: Lab](../README.md)

`execution-policy` is an H configuration surface for fixed Core runtime settings.
It has no Improvement optimization target. Configuration does not imply editable
experiment scope or a replaceable execution algorithm.

| Setting | Default | Behavior |
|---|---:|---|
| `max_tool_calls_per_turn` | 512 | Daily per-turn tool allowance; 0 prevents calls |
| `max_turns` | 32 | Daily assistant-turn allowance |
| `max_context_recovery_attempts` | 6 | Consecutive context recovery allowance |
| `tool_execution.max_parallel` | 8 | Concurrent calls in an eligible tool batch |
| `tool_execution.default_execution_mode` | parallel | Default tool-batch execution mode |

## Permit selected changes

Change `parameters.settings` in the system component document through the ordinary
[runtime specification](../../runtime_spec/COMPONENTS.md). Unknown fields fail.
These settings are fixed conditions during Improvement. Editor, evaluator and
trial invocations remove tool/turn count caps and use independent stage times.
Mechanism-owned execution fields retain their declared owner checks.

Run records effective settings in RuntimeManifest; compatible task backends can
also retain `runtime-execution.json`. Neither configuration nor selection grants
activation of arbitrary code.

## Verify offline

`tests.run.test_execution_limits` checks live configuration and fixed trial
settings. `tests.workflows.test_execution_policy` checks rejected optimization
grants, continuation isolation and the separate Bash timeout surface.
