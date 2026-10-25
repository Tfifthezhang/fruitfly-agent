# Tool Runtime

[Up: Core](../README.md)

Validate arguments and dispatch tools. Concrete factories belong in [Lab Tools](../../lab/tools/README.md).

| Contract | Responsibility |
|---|---|
| `AgentTool` | Name, display label, model-facing description, parameter schema, and `execute` |
| `ToolCallContext` | Call ID, validated arguments, environment, updates, and cancellation signal |
| `AgentToolResult` | Result converted by Core into `ToolResultMessage` |
| [schema.py](schema.py) | Supported JSON Schema subset and primitive coercion |
| [execution.py](execution.py) | Remaining-budget batch dispatch, sequential/parallel execution, hooks, and result conversion |

Invalid arguments and ordinary tool failures become error tool results. Tools use the injected execution environment. Add concrete operations in Lab rather than Core. No module-specific environment variables.

`AgentToolResult.error(...)` explicitly marks a failed result. Core preserves its
`is_error` flag and records actual dispatch facts separately: rejected/attempted
calls do not imply that a tool body started. See [loop diagnostics](../README.md#runtime-rules).

```bash
.venv/bin/python -m unittest tests.core.test_schema tests.core.test_loop tests.lab.test_builtin_tools -v
```

## Authorize final calls

[authorization.py](authorization.py) defines `ToolPermission`, `AuthorizationRequest`, `AuthorizationDecision`, `AuthorizationPrompt`, and the execution-scoped `ToolAuthorizer` protocol. Tool declarations describe an operation and any path argument names; Core does not interpret concrete tools or path policy.

Core authorizes after argument preparation, active hooks, and final schema validation. Only an explicit valid allow decision executes. Authorization exceptions, invalid decisions, and changed authorization arguments produce an error tool result. Cancellation propagates. The authorization context stays active during execution and exits before result hooks.

Direct Core callers may omit `AgentLoopConfig.tool_authorizer` for compatibility; that provides no permission enforcement. Standard [Run assembly](../../run/README.md) always supplies it. Ordinary Hook failure isolation remains unchanged. Custom tools must declare `permission` when used with the standard host policy; unknown operations are denied.

Lab's host policy also recognizes `network_read` declarations for selected [web tools](../../lab/tools/web/README.md). Core still forwards operation metadata without interpreting destination rules or service credentials.

## Observe tool calls

`AgentTool.label` is the short user-facing action. Optional `describe_call(arguments)`
returns a call-specific action description. Interactive invokes it with a private
argument copy and falls back to the label/name on empty, invalid, or failing output.
Descriptions contain plain text, carry no execution authority, and do not enter the
model schema. Concrete wording belongs to tool factories in Lab.

`AgentLoopConfig.on_tool_result(name, result, cancelled)` observes each result from
a dispatched batch, including lookup/validation failures, hook blocking, permission
denial, execution errors, budget rejection and cancellation. The result is a private
`ToolResultMessage` copy. Ordinary callback failures are isolated; callback cancellation
propagates. Existing success-only `after_tool_call` and `AFTER_TOOL` rewriting semantics
remain unchanged. Calls skipped because of a truncated model response are recorded
by the loop outside batch dispatch and do not invoke this callback.

The cancellation flag identifies interrupted or unexecuted calls in an aborted batch;
it does not imply rollback. Completed calls retain their actual outcomes. Call IDs
associate concurrent results; callbacks do not guarantee completion order.
