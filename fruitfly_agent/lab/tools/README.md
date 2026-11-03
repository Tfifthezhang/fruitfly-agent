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
| [media.py](media.py) | `create_save_media_tool` using host-granted resources and the shared Core media limits |
| [ipython.py](ipython.py) | `create_ipython_tool`: explicit Python workspace integration |
| [catalog.py](catalog.py) | One editable tool policy; detailed usage through scoped read-only resources |
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

Enable optional `save-media-tool` through ordinary configuration. It installs
`save_media(resource_id, path)`, separate from text-only `write(path, content)`.
Run grants IDs from user attachments and image tool results. The tool reads only
granted resources, verifies content hashes, then writes original bytes (up to
10 MiB) through `ctx.env.write_file`, the normal write permission and mutation
queue. SSH destinations stay remote; resource storage stays local. IDs are not
arbitrary artifact paths. The tool does not generate or convert media.

Media operations retain their fixed schema and implementation. Their detailed usage
joins the shared Tool catalog. An Improvement backend must explicitly declare
and supply media-saving capability and its resource grants. Media grants are Session-owned and restored after hash
checks; no cross-Session sharing or automatic resource collection is added.

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
exposes concise API descriptions and demand-loaded details when `read` is enabled.

## Describe visible operations

`tool-catalog` is one H optimization target. Its `parameters.instructions.usage`
coordinates tool selection, composition, failure recovery and verification. Names,
schemas, permissions, implementations and individual usage documents stay fixed.
The policy accepts 1–12000 characters. It uses ordinary artifact binding,
configuration export, isolated trials, verified activation and recovery.

| Model input | Content |
|---|---|
| System projection | Overall policy, actual tool names/labels and full-usage references |
| API tool definition | Short operation description and original argument schema |
| `read(resource://…/tools/<name>.txt)` | Full source-owned usage for the selected tool |

Details are loaded only when the model calls the existing `read` tool. No loader
tool is added. Resources are scoped to the runtime, read-only, and independent of
local/SSH paths. Closing the runtime retires them. Hidden tools are omitted.
A runtime without visible `read` retains inline descriptions so usage remains
accessible. Loading is instruction-driven, not an enforced precondition on calls.

Factories must supply complete, standalone usage and concise labels. New tools,
including prepared external tools, automatically join the assembled catalog.
No per-tool optimization slots are registered. The catalog's defaults and exact
adopted policy are exported by the shared configuration path. Its standalone
surface requires no separate installer; the instruction owner prepares it after
all tools exist. Candidate backends must derive references from their own tool
set and fresh resource scope, without borrowing the daily catalog.

Tool parameter targets remain discoverable, but `default_selected: false` keeps
them out of automatic CLI and chat edit scope. Explicit experiment grants can
select supported parameters with an appropriate execution backend. This does not
change model-supplied arguments such as one Bash call's `timeout`.

Offline checks: `tests.lab.test_tool_catalog`, `tests.lab.test_component_targets`,
`tests.workflows.test_improvement`, `tests.experiments.test_harness_validation`.

## Bound and manage shell commands

Bash defaults to a 600-second timeout. A positive finite `timeout` overrides it.
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

[tool-catalog.yaml](tool-catalog.yaml) owns the H tool policy;
[bash-tool.yaml](bash-tool.yaml) owns Bash parameter defaults. Registry, menu and
constructor values derive from these documents. Candidate parameter YAML shares
the same typed validation for instructions and numbers. Tool names, schemas,
permissions and individual operation contracts remain protected.

Assembly records full-usage and Schema SHA-256 fingerprints before shortening API
descriptions. Run retains them in `harness.tool_contracts`; short API descriptions
alone are not the complete usage identity. Fresh runtimes rebuild these resources;
existing resources remain scoped and immutable until closure.
