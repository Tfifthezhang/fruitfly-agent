# Tools

[Up: Lab](../README.md)

File, shell, IPython and public web operations implementing Core's `AgentTool`. Local tools use the host's execution environment; web tools use injected HTTP clients.

Read, write, edit and Bash use the selected backend, including the optional
[SSH environment](../environment/methods/remote/README.md). IPython remains local and is
incompatible with the SSH selection.

## Factories and files

| File | Factory / responsibility |
|---|---|
| [builtin.py](builtin.py) | `builtin_tools()` collects the file and shell tools. |
| [read.py](methods/read/algorithm.py) | `create_read_tool`: text pagination and image reading |
| [bash.py](methods/bash/algorithm.py) | `create_bash_tool`: commands and live output |
| [edit.py](methods/edit/algorithm.py) | `create_edit_tool`: unique, non-overlapping text replacement |
| [write.py](methods/write/algorithm.py) | `create_write_tool`: file writes |
| [ipython.py](methods/ipython/algorithm.py) | `create_ipython_tool`: explicit Python workspace integration |
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
| Long lines | Clip on a complete UTF-8 character boundary. Character pagination retrieves omitted characters from the same line. |
| Bash failure/cancellation | Bound output; advertise the complete log only after a successful write. User-signal cancellation propagates as task cancellation; timeout/backend abort without that signal remains an error. |
| Bash log persistence | Attempt to save truncated output; report save failures without advertising a complete log. |
| Truncation API | Nonnegative integer budgets; zero gives an empty body; negative, boolean, or noninteger budgets raise `ValueError`. |

Reads still load entire files. Image results are limited to 10 MiB and validated
as PNG/JPEG/GIF/WebP containers; PNG dimensions are bounded to 40 megapixels.
Container checks do not fully decode pixels. Unsupported binary files and invalid
UTF-8 fail explicitly. BMP is rejected instead of being passed to an incompatible
image API. Path locks coordinate only this process. See [Known limitations](../ALGORITHM_AUDIT.md).

## Save a media resource

Use `write` with `path` and exactly one of `content` or `resource_id`. Text uses
`content`; a granted media resource uses `resource_id` to save its original bytes
without base64 arguments. The same file authorization, read-only resource checks,
mutation queue and local/remote environment apply. Ungranted IDs and resources
above 10 MiB fail before writing. Media registration/recovery remains host-owned.

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

## Observe operations

Built-in labels describe the action: Read file, Write file, Edit file, Execute shell
command, Execute Python code, Search the web and Fetch web page. Parameters supply
paths, commands and queries separately. The terminal does not maintain a tool-name
lookup table. Custom tools inherit the same label/name fallback.

Bash accepts an optional `description` string describing the current command's
purpose, such as `Run menu tests`. Its `describe_call` callback uses that value only
for observation; it does not change the command, timeout, authorization or outcome.
Omission or blank text uses the tool label. Do not include credentials in descriptions.
The factory's full `description` is source-owned tool usage. Catalog assembly
preserves the complete native API description and argument schema.

## Describe and improve native tools

Each tool sends its complete description and original parameter schema directly
to the Provider. Its owner registers `instructions.description` as an H editing
surface alongside explicitly allowed settings. There is no independent tool
catalog policy, resource loader or extra read requirement.

Tool names, schemas, implementations and permissions remain protected. Parameter
targets default to `default_selected: false`; explicit grants and a capable
isolated runner are required. Candidate assembly replaces only the declared fields
and records actual description/schema fingerprints in `harness.tool_contracts`.
MCP remains a service source producing distinct native tools. External schemas,
transport and authorization are protected, and unsupported isolated trials fail.

[registration.py](registration.py) composes native tools; [improvement.py](improvement.py)
binds owner parameter adapters. Each implementation and its canonical defaults live
under `methods/<name>/`. [Web](web/README.md) owns service adapters; [IPython](methods/ipython/README.md)
owns its process and model bridge. Shared file queues and resource access stay at
module level.

Offline checks: `tests.lab.test_tool_instructions`, `tests.lab.test_parameter_candidates`
and `tests.workflows.test_multimodal`.

## Bound and manage shell commands

Bash defaults to a 300-second timeout. A positive finite `timeout` overrides it.
For long work, call Bash with `action: start`, `command` and optional
`wait_seconds` (default 0.2, range 0–30); it returns a runtime-owned handle.
Use `action: poll` with `handle` for bounded output or `action: cancel` to retire
that command. Omitted action runs synchronously. The initiating task cancellation signal and runtime closure both cancel managed
jobs; closure requires backend cleanup confirmation. Handles are local to that runtime.

The `bash-tool` component declares `default_timeout_seconds` (1–28800),
`max_active_commands` (default 4, 1–16), `retained_commands` (default 128, 16–256)
and `output_characters` (default 12000, 100–24000). Completed old handles can be
retired when capacity is reached; active work is never evicted to start another.
`default_timeout_seconds` is the only optimizable Bash parameter. Active-job,
retained-handle and output-page limits remain fixed experiment conditions.
Bash candidates require both configuration materialization and Bash execution. A larger command timeout never extends its parent
operation or experiment deadline. Managed tasks are in-process capabilities, not
persistent remote jobs or an OS sandbox. All actions retain execution permission.
Command deadlines cover process exit and output collection. Timeout/cancellation
uses a separate bounded cleanup interval; an unconfirmed cleanup is an error and
prevents reuse of the affected backend. See [environment execution](../environment/README.md).

Offline checks: `tests.lab.test_managed_commands`, `tests.lab.test_parameter_candidates`.

Text reads also support `character_offset` (zero-based) and `character_limit`
(1–24000, default 12000), mutually exclusive with line offset/limit. This permits
complete readback of long single-line history through the existing tool. Every
response retains the tool byte/line bounds and a precise continuation offset.

## Present structured facts

Tools may declare `present_call(arguments)` and `present_result(result)` callbacks
returning Core `ToolPresentation` values. [presentation.py](presentation.py)
contains shared deterministic file/text helpers. The callbacks supply a bounded
operation, target, summary, detail items and execution state. They do not call
models, execute commands, inspect unrelated state or decide task success. Callback
failures fall back to ordinary labels/output. `describe_call` remains available
for a concise action label. Shell commands are displayed literally; shell syntax
is not interpreted to infer read/write intent.

Interactive projects these facts into `ToolStarted` and `ToolFinished`, with call
IDs and attributed `ToolOutput`. Terminal rendering keeps the existing category
and outcome colors, escapes control sequences and bounds output independently of
model context. A background start shows Running rather than Completed.

## Own background operations

[managed.py](managed.py) owns the generic in-process operation service: bounded
active/retained handles and output, elapsed time, correlated run/call IDs, isolated
notifications and confirmed cancellation. [commands.py](commands.py) adapts shell
results to this service. Runtime ownership closes it; shared close is idempotent.
Failed cancellation is `cleanup_unconfirmed`, never success. Status and completion
notifications do not invoke the model. There is no persistent job restart or
scheduler for multiple independent user conversations.

Run optionally adapts this service to Interactive's `OperationService`; the
registered terminal `/operations [cancel HANDLE]` command consumes only that
capability. Existing Bash `start`, `poll`, `cancel` remain model-callable. Start
returns control so the Agent can perform independent work; poll before depending
on the result. Ordinary synchronous tools and model requests remain awaited.

## Keep defaults and usage identities

Each method's `defaults.yaml` owns its complete description and declared settings.
Factories, Catalog parameters, candidates and exports derive from that resource.
Assembly fingerprints actual tool descriptions and schemas without shortening
them. These identities describe instructions/contracts, not evidence of tool use
or model quality. Runtime resources retire when their owning runtime closes.

