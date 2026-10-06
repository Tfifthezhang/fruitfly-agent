# Tools

[Up: Lab](../README.md)

File, shell, and IPython operations implementing Core's `AgentTool`. Tools use the execution environment supplied by the host.

## Factories and files

| File | Factory / responsibility |
|---|---|
| [builtin.py](builtin.py) | `builtin_tools()` collects the file and shell tools. |
| [read.py](read.py) | `create_read_tool`: text pagination and image reading |
| [bash.py](bash.py) | `create_bash_tool`: commands and live output |
| [edit.py](edit.py) | `create_edit_tool`: unique, non-overlapping text replacement |
| [write.py](write.py) | `create_write_tool`: file writes |
| [ipython.py](ipython.py) | `create_ipython_tool`: explicit Python workspace integration |
| [truncate.py](truncate.py) | Head/tail output limits |
| [path_utils.py](path_utils.py), [file_queue.py](file_queue.py) | Path normalization and in-process mutation ordering |

Inject `builtin_tools()` into `AgentLoopConfig.tools`. IPython is added explicitly. Local tools may write files and execute commands with your current user permissions; no module-specific environment variables or sandbox.

## Observable behavior

| Operation | Contract |
|---|---|
| Write | Create or replace text through the environment; report the number of Python string characters, not encoded bytes or displayed glyphs. |
| Edit | Locate every replacement in the original file before writing; require unique, non-overlapping spans. |
| Fuzzy edit | Compare whole-line spans; reject tied best matches and empty `oldText`. |
| Read/bash output | Default body limit: 2000 lines and 51200 UTF-8 bytes; notices are separate. |
| Long lines | Clip on a complete UTF-8 character boundary. Read offsets cannot retrieve omitted characters from the same line. |
| Bash failure/cancellation | Bound output; advertise the complete log only after a successful write. |
| Bash log persistence | Attempt to save truncated output; report save failures without advertising a complete log. |
| Truncation API | Nonnegative integer budgets; zero gives an empty body; negative, boolean, or noninteger budgets raise `ValueError`. |

Reads still load entire files. Images and other tool errors lack shared size budgets. Path locks coordinate only this process. See [Known limitations](../ALGORITHM_AUDIT.md).

## Add a tool

| Concern | Required behavior |
|---|---|
| Declaration | Unique name, description, supported JSON Schema, and `execute(ctx)` |
| Execution | Sync or async; return `AgentToolResult`; Core turns ordinary exceptions into error results. |
| Environment | Use `ctx.env`; define behavior when it is missing. |
| Updates and cancellation | Use `ctx.on_update` and `ctx.signal`; propagate task cancellation and clean resources. |
| Concurrency | Declare parallel/sequential mode and a policy for shared state. |
| Output | Bound output and explain truncation. |
| Assembly | Append tools rather than replacing existing ones; declare external effects in Catalog. |

Use [Core tool contracts](../../core/tool_runtime/README.md), [Environment](../environment/README.md), and [Catalog](../catalog/README.md).

```bash
.venv/bin/python -m unittest tests.lab.test_builtin_tools -v
```
