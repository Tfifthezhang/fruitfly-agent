# Tool Runtime

[Up: Core](../README.md)

Validate arguments and dispatch tools. Concrete factories belong in [Lab Tools](../../lab/tools/README.md).

| Contract | Responsibility |
|---|---|
| `AgentTool` | Name, description, parameter schema, and `execute` |
| `ToolCallContext` | Call ID, validated arguments, environment, updates, and cancellation signal |
| `AgentToolResult` | Result converted by Core into `ToolResultMessage` |
| [schema.py](schema.py) | Supported JSON Schema subset and primitive coercion |
| [execution.py](execution.py) | Remaining-budget batch dispatch, sequential/parallel execution, hooks, and result conversion |

Invalid arguments and ordinary tool failures become error tool results. Tools use the injected execution environment. Add concrete operations in Lab rather than Core. No module-specific environment variables.

```bash
.venv/bin/python -m unittest tests.core.test_schema tests.core.test_loop tests.lab.test_builtin_tools -v
```

## Authorize final calls

[authorization.py](authorization.py) defines `ToolPermission`, `AuthorizationRequest`, `AuthorizationDecision`, `AuthorizationPrompt`, and the execution-scoped `ToolAuthorizer` protocol. Tool declarations describe an operation and any path argument names; Core does not interpret concrete tools or path policy.

Core authorizes after argument preparation, active hooks, and final schema validation. Only an explicit valid allow decision executes. Authorization exceptions, invalid decisions, and changed authorization arguments produce an error tool result. Cancellation propagates. The authorization context stays active during execution and exits before result hooks.

Direct Core callers may omit `AgentLoopConfig.tool_authorizer` for compatibility; that provides no permission enforcement. Standard [Run assembly](../../run/README.md) always supplies it. Ordinary Hook failure isolation remains unchanged. Custom tools must declare `permission` when used with the standard host policy; unknown operations are denied.
