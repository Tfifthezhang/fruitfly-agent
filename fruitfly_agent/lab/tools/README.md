# Tools

[Up: Lab](../README.md)

File, shell, IPython and public web operations implementing Core's `AgentTool`. Local tools use the host's execution environment; web tools use injected HTTP clients.

Read, write, edit and Bash use the selected backend, including the optional
[SSH environment](../environment/ssh/README.md). IPython remains local and is
incompatible with the SSH selection.

## Factories and files

| File | Factory / responsibility |
|---|---|
| [builtin.py](builtin.py) | `builtin_tools()` collects the file and shell tools. |
| [read.py](read.py) | `create_read_tool`: text pagination and image reading |
| [bash.py](bash.py) | `create_bash_tool`: commands and live output |
| [edit.py](edit.py) | `create_edit_tool`: unique, non-overlapping text replacement |
| [write.py](write.py) | `create_write_tool`: file writes |
| [ipython.py](ipython.py) | `create_ipython_tool`: explicit Python workspace integration |
| [guidance.py](guidance.py) | `ToolGuidanceTarget`: validate, trial and bind instruction text independently of tool implementations |
| [Web tools](web/README.md) | `web_search` through Brave/Tavily/DeepSeek; `web_fetch` directly or through DeepSeek; disabled by default |
| [truncate.py](truncate.py) | Head/tail output limits |
| [path_utils.py](path_utils.py), [file_queue.py](file_queue.py) | Path normalization and in-process mutation ordering |

Inject `builtin_tools()` into `AgentLoopConfig.tools`. IPython is added explicitly. Local tools may write files and execute commands with your current user permissions; no module-specific environment variables or sandbox.

## Observable behavior

| Operation | Contract |
|---|---|
| Paths | Preserve ASCII punctuation, including hyphens. Convert U+00A0, U+2000–U+200A, U+202F, U+205F, and U+3000 to spaces and strip a leading `@`; reads also try documented Unicode filename variants. |
| Write | Create or replace text through the environment; report the number of Python string characters, not encoded bytes or displayed glyphs. |
| Edit | Locate every replacement in the original file before writing; require unique, non-overlapping spans. |
| Fuzzy edit | Compare whole-line spans; reject tied best matches and empty `oldText`. |
| Read/bash output | Default body limit: 2000 lines and 51200 UTF-8 bytes; notices are separate. |
| Long lines | Clip on a complete UTF-8 character boundary. Read offsets cannot retrieve omitted characters from the same line. |
| Bash failure/cancellation | Bound output; advertise the complete log only after a successful write. User-signal cancellation propagates as task cancellation; timeout/backend abort without that signal remains an error. |
| Bash log persistence | Attempt to save truncated output; report save failures without advertising a complete log. |
| Truncation API | Nonnegative integer budgets; zero gives an empty body; negative, boolean, or noninteger budgets raise `ValueError`. |

Reads still load entire files. Images and other tool errors lack shared size budgets. Path locks coordinate only this process. See [Known limitations](../ALGORITHM_AUDIT.md).

## Add a tool

| Concern | Required behavior |
|---|---|
| Declaration | Unique name, concise display `label`, model-facing description, supported JSON Schema, and `execute(ctx)` |
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

Built-in tools declare `ToolPermission`: read is a file read, edit/write are file writes, and Bash/IPython are local execution. The standard host authorizes final arguments and injects the [guarded environment](../environment/README.md#apply-lightweight-permissions). Custom tools must declare their operation/path arguments; declarations are trusted plugin metadata, not proof that arbitrary plugin code respects a boundary.

Web tools declare `network_read`; host-owned `PermissionPolicy.allow_network` can deny them. See the [web guide](web/README.md) for credentials, HTTP limits and caches. `builtin_tools()` remains the four local file/shell factories; Catalog registers web tools separately.

## Describe visible operations

Built-in labels describe the action: Read file, Write file, Edit file, Execute shell
command, Execute Python code, Search the web and Fetch web page. Parameters supply
paths, commands and queries separately. The terminal does not maintain a tool-name
lookup table. Custom tools inherit the same label/name fallback.

Bash accepts an optional `description` string describing the current command's
purpose, such as `Run menu tests`. Its `describe_call` callback uses that value only
for observation; it does not change the command, timeout, authorization or outcome.
Omission or blank text uses the tool label. Do not include credentials in descriptions.
The model-facing `description` remains the full tool usage instructions.

Each tool owns its use cases, scope and limits in that description. Descriptions
must stand alone when only that tool is enabled; do not name another tool as a
required next step. Providers serialize the enabled tools' descriptions into API
tool definitions. The base prompt does not enumerate tools or prescribe their
selection. These descriptions guide model choice; they do not enforce routing.

| Tool | Use cases declared to the model |
|---|---|
| Read | Inspect source, configuration, logs and saved artifacts in the selected local or SSH environment. |
| Write | Create or replace a complete text file in that environment. |
| Edit | Make targeted replacements while preserving surrounding content in that environment. |
| Bash | Inspect the environment, run programs, install, build, test, download files and process API responses there. |
| IPython | Calculate, analyze data and reuse Python state in a local workspace. |
| Search | Discover external information, check current facts and locate authoritative sources. |
| Fetch | Read a known URL and verify details or quotations, within the selected service's capabilities. |

## Bind an instruction candidate

The built-in Catalog exposes one H target `tool-guidance.<name>` per enabled tool,
plus the combined [execution instruction target](../algorithms/README.md#improve-multiple-instruction-components).
An adopted guidance artifact replaces only `AgentTool.description`; it keeps the
name, parameters, execution function and permission declaration. Each complete
description must be nonempty and at most 6000 characters. Artifacts are consumed
at runtime construction and recorded in H identity. Disabling a tool with a bound
artifact requires clearing that binding; unused bindings fail construction.

Custom tool definitions can declare the slot returned by `guidance_key(name)` in
`artifact_slots`. `prepare_guidance` consumes enabled tools' bindings and registers
their object-owned targets. The built-in composition root supplies those slots
from its declared tool effects. Installing a description does not invoke the tool
or make a model request. Component experiments require isolated full-runtime
execution; ordinary tool-free text trials are not a measurement of tool use.
