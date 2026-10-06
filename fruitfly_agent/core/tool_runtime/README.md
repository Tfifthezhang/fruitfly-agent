# Tool Runtime

[Up: Core](../README.md)

Validate arguments and dispatch tools. Concrete factories belong in [Lab Tools](../../lab/tools/README.md).

| Contract | Responsibility |
|---|---|
| `AgentTool` | Name, description, parameter schema, and `execute` |
| `ToolCallContext` | Call ID, validated arguments, environment, updates, and cancellation signal |
| `AgentToolResult` | Result converted by Core into `ToolResultMessage` |
| [schema.py](schema.py) | Supported JSON Schema subset and primitive coercion |

Invalid arguments and ordinary tool failures become error tool results. Tools use the injected execution environment. Add concrete operations in Lab rather than Core. No module-specific environment variables.

```bash
.venv/bin/python -m unittest tests.core.test_schema tests.core.test_loop tests.lab.test_builtin_tools -v
```
