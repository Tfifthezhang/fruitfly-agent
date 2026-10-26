# Terminal

[Up: Interactive](../README.md)

Use FruitFlyAgent through stdin/stdout, menus, and live events. Application owns sessions and work; this frontend handles input and display.

## Daily use

| Need | Action |
|---|---|
| Start | Run `python -m fruitfly_agent`; choose **Start new session**. |
| Configure | `/config`; save and apply to this conversation, or save only. |
| Select a prompt | **Configure → prompt** or `/config`; preview and confirm. |
| Complete a command | Type `/` or a prefix, use ↑↓ to select and Tab to fill it; Enter submits the current text, Esc hides suggestions. |
| Copy text | Use native terminal selection and its copy shortcut. |
| Browse earlier chat | Scroll with the terminal's mouse wheel, touchpad or scrollback controls. |
| Inspect activity | `/status`: model, prompt, workspace, session, committed conversation message count, state, queue, pending candidates, context usage bar/percentage, and session compaction count. |
| Inspect the active harness | `/lab`: active context mechanisms, execution environment, installed tools and supplied capabilities. |
| Cancel active work | `/cancel` or the first Ctrl+C; clear pending Application input. |
| Exit | `/exit`, `/quit`, or a second Ctrl+C within three seconds; drain cancelled work before resource cleanup. |
| Clear a draft | First Ctrl+C while idle; normal submitted input resets the double-press interval. |
| Restore a conversation | `/resume` to choose a session; `/resume PATH` to switch directly. |
| Review live details | `/trace` |
| Search or review candidates | `/improvement [DIRECTION]` |

POSIX ANSI terminals support live input, history, cancellation, and bracketed paste. Non-ANSI POSIX TTY input uses a stoppable canonical reader and handles SIGINT while a run is waiting. Redirected input uses sequential line-based fallback and cannot consume `/cancel` during a run. Display limits do not alter model context or stored messages. `NO_COLOR` and terminal capabilities affect rendering.

The editable input area has a contrasting background, an emphasized `❯` prefix, and vertical spacing without full-width borders. Submitted inputs retain an emphasized prefix and blank lines, without background fill. The input uses a neutral gray background and the terminal’s default text color, with light/dark hints and capability fallbacks described in [I/O](io/README.md); `NO_COLOR` keeps the text and spacing. The built-in POSIX ANSI frontend appends completed chat to the main screen and redraws only its live tail. Mouse capture stays off. Earlier chat remains in terminal scrollback after menus and exit, subject to the terminal's scrollback limit. Resizing retains the draft and cursor; the terminal owns committed history, which the application does not reformat or replay. Temporary menus use an alternate screen and restore chat on return. Redirected and non-ANSI streams retain linear output.

Embeddings may explicitly request the optional fullscreen display, with its separate browsing and copy controls described in [I/O](io/README.md). The built-in chat does not require F2/F3 for browsing or selection. Terminal modes remain presentation state, outside Agent configuration and Session persistence.

Live reasoning text is hidden. The existing activity display indicates reasoning, answer reception, and tool execution; redirected output keeps brief activity milestones without animation. Reasoning summaries are also hidden. This presentation policy adds no model requests and does not change reasoning usage. Ordinary assistant text and bounded tool output remain visible.

## Complete a command

The built-in ANSI chat editor suggests registered commands as you type the first
slash token. Candidates show descriptions and argument usage. Up/Down selects a
candidate; Tab replaces only the command token and keeps surrounding text. Enter
submits the existing draft without accepting a suggestion. Esc hides the list until
the text or cursor changes and restores normal input-history navigation. Candidate
rows scroll within a bounded area and are never added to conversation history.

Ordinary text, command arguments, multiline input and multi-segment paths do not
trigger suggestions. Bracketed paste retains literal tabs and newlines. Permission
input, copy mode and configuration/secret fields take priority. Redirected and
non-ANSI input keep their existing line behavior. Completion makes no model,
filesystem or command-handler requests.

## Restore a conversation

After successful `/resume` or interactive startup with `--resume`, the terminal appends the original conversation in chronological order, followed by an end marker and the normal input prompt. User and assistant text is complete; ANSI terminals format assistant Markdown. Use native terminal scrollback to review earlier turns. Menus restore the main screen without replaying runtime events. Linear fallback remains available for other streams.

Tool calls show names without arguments. Tool results show at most 800 characters per message and explicitly mark omitted output. Images show attachment/media-type markers; reasoning shows an omission marker. Internal context summaries and transient activity events are not replayed. History display makes no model requests, executes no tools, and writes no messages. Context reduction may still affect the context sent to the model.

Cancelled or failed restoration keeps the current session and does not display the target history. Embedding hosts can optionally expose `conversation()` using the [Interactive views](../README.md#state-and-events); existing terminal hosts without it continue to work. A single-task CLI run with `--resume` continues saved context without printing the historical conversation.

## Configure

The home menu retains Start new session, Configure and Exit. **Restore default
configuration** appears immediately before Back in Configure and `/config`. It
stages the default prompt, mechanisms and bindings while preserving the current
model and credentials. Review and apply the saved draft to this conversation,
save only, or discard the changes.
Default files are edited manually. No permission configuration page is supplied.

| Menu | Behavior |
|---|---|
| `model` / `prompt` | Stage the model and prompt for review and explicit application. |
| Add model… | Collect host-provided service fields, hidden API key, and review; stage until configuration save. Opens on first startup when no models exist. |
| Set API key… | Stage a missing credential for the selected model; the menu shows only set/missing status. |
| Tools → Set up… | Select a web service and optional key variable, enter a hidden API key, and stage until configuration save. Direct fetch skips key input. |
| Context, Tools, Environment | One readable row per mechanism; Enter expands algorithm choices and descriptions, Details reveals paths/configuration locations, Space enables/disables. |
| Context sections | Augmentation groups Skills, Memory, Knowledge and HTTP; externalization and reduction remain separate sections on the same page. |
| Algorithm selector | Multiple implementations use inline radio choices; sole implementations expose a description with expandable Details. |
| User inputs | Edit declared paths, initial text and endpoints with visible input; tune internal parameters in the displayed YAML location. |
| Prompt results | Current configuration/profile's latest task-scoped prompt candidates, plus built-ins and current selection |

Expanding a prompt group does not change configuration. Choosing a prompt opens a full preview and confirmation. Saving alone retains the active runtime. **Save and apply to this conversation** rebuilds it through recovery while retaining the Session file and messages. Failure retains the incumbent; saved files remain saved. Approval grants and transient component state are recreated. See [Configuration](../../../CONFIGURATION.md#apply-settings-to-the-current-conversation).

Selecting a service replaces the choice menu with one field per screen. Each field shows the selected service, step count, its purpose, and any default. Field prompts use the field name; conversation input uses `❯`. Official and custom services have separate address instructions. `models.<name>` is the menu name; `model` is the service's exact identifier. Other fields use their YAML keys.

The `capabilities` page renders host-provided booleans as checkboxes with defaults. Space or Enter toggles the selected capability; Continue confirms. Choices limited to one value remain fixed and explain the requirement. Checked values are staged as `true`, unchecked values as `false`; cancel discards the page. The host remains responsible for capability validation.

Model forms accept `/cancel` or EOF without staging. Review includes the selected service and defaults to Cancel. API key input disables TTY echo and bypasses readline/history; redirected input is read directly without writing its value to output. The host validates and saves settings; the terminal performs no Provider requests or filesystem configuration writes.

Enumerated fields use registered choices with arrow-key selection and Enter confirmation; line-based menus use numbered choices. The same chooser serves editable mechanism parameters and setup forms. Unknown choices remain invalid in host validation.

Mechanism forms refresh credential requirements from pending non-secret field
values before hidden input. Switching a service or key variable changes the
binding within that form. `/clear` clears an ordinary field; required-field
validation still applies. Hidden input and review reuse the model form's echo,
history, cancellation and staging behavior. The host owns secret-file writes.

## Improve against a task set

`/improvement [DIRECTION]` opens a small task-material panel for one simple
base-prompt comparison. Choose explicit instructions/files or a saved package,
then review the frozen preview before submission. Advanced H/S/I experiments,
models, strategies and allocations use the independent experiment CLI and files;
chat does not edit experiment configuration.

| Action | Behavior |
|---|---|
| Start improvement | Fresh preview and one confirmation, defaulting to Cancel; model work may incur charges |
| Task / Input files | Select explicit task materials |
| Pending experience | Review and explicitly commit or reject lessons while idle |
| Return to chat while running | Continue Application-owned work; inspect `/status`, `/cancel`, or Results and history |
| Results and history | Inspect every submitted run, including empty, failed and cancelled experiments |
| Review candidate | Assessment, comparison, usage, changes, original/candidate text, scope and evidence |
| Set as next-session default | Confirm a saved configuration change without replacing the active session |
| Set default and start a new session | Confirm the default change and open an empty session |

Back/Esc cancels active field input, then collapses a section, then returns to chat. Draft fields remain intact. `q` exits menu mode and is literal text during field input. Cyan focus and green enabled/selected markers remain distinct; Modified/warnings use yellow and errors use red. Section titles and indentation express hierarchy. Raw-key menus omit row numbers; line fallback retains them. `NO_COLOR` preserves symbols and text. Confirmation always starts with Cancel selected. Detail actions default to Back; `n`/`p` switch sections, PageUp/PageDown page text. Numbered fallback accepts next/previous and pageup/pagedown. Cancellation and outcomes remain visible after restoring chat. Candidates are already stored and do not guarantee improvement.

Current tasks and saved packages use the same running/result flow. Raw TTY input polls through the existing reader to refresh progress and offer return/cancel actions. Redirected/non-polling input waits for completion and cannot consume `/cancel` during the wait. Progress measures the current batch, not overall completion. Results expose the stop reason and measured evidence even when no candidate is published. See the [feature guide](features/improvement/README.md).

## Inspect the active harness

The welcome block, `/lab` and `/status` distinguish the local workspace from the
active file/Bash execution environment. Local execution shows its directory;
SSH execution also shows the server and port. Long locations wrap completely.
Sessions, configuration and context resources remain local. These views describe
the activated runtime, not a configuration draft or a continuous connection-health
check. Failed replacement retains the previous target. Hosts without execution
metadata show Unavailable rather than assuming local execution.

`/lab` inspects the current runtime, including tools and execution capabilities.
It reads a supplied status snapshot, so saved configuration drafts do not appear
as active. Unselected algorithms remain available through `/config`. Hidden
internal aggregation components stay hidden. Improvement appears as Available
only when the host supplies the component-workflow capability; inspection starts
no work.

Section titles have compact color blocks. Bodies remain unfilled and use aligned
rows, with explicit Not enabled text for empty context phases. Example content
for a runtime with an SSH backend:

```text
Lab · Active session

Context Manager
  Augmentation     Skill catalog
  Externalization  Not enabled
  Reduction        Summarizing

Environment
  Local workspace        /Users/example/fruitfly-agent
  Execution environment  Remote SSH
  Server                 server.example:2222
  Execution directory    /srv/project
  Remote environment  Enabled

Tools
  read   Read files
  bash   Run shell commands

Improvement
  Component workflow  Available · /improvement
```

Actual rows follow host-provided runtime metadata. Unknown categories and missing
phase metadata remain visible. Narrow windows stack and wrap rows; `NO_COLOR`,
dumb terminals and redirected output retain the same sections without color.

## Register a command

`TerminalFrontend(command_handlers={...})` accepts synchronous or asynchronous handlers. Each receives an `InteractiveCommand` and returns a `CommandResult`. The frontend forwards results to the renderer and handles exit; handlers capture only the service operations they need. Registered terminal commands run before the frontend-neutral CommandRouter fallback. Results may provide a read-only `CommandPanel` alongside their plain-text fallback; the renderer chooses the layout without adding command-specific input-loop branches.

```python
from fruitfly_agent.interactive.interaction.commands import CommandResult
from fruitfly_agent.interactive.terminal import TerminalFrontend

# application is an already constructed host. This example makes no model request.
async def describe(command):
    return CommandResult(text=f"Runtime: {application.runtime_manifest['digest']}\n")

frontend = TerminalFrontend(application)
frontend.commands.register("describe", describe, summary="Show the runtime identity")
# await frontend.run() starts terminal input.
```

Names are lowercase, path-free tokens. Duplicate registration raises an error. Terminal descriptions override same-name base descriptions in the same order as execution; `/quit` retains its `/exit` alias. `frontend.commands.register(name, handler, replace=True)` explicitly replaces a registered terminal handler. `/quit` is parsed as `/exit`. Custom commands appear in default `/help` and completion automatically. Optional `summary`, `usage` and `discoverable` registration fields control discovery. Hidden registrations still retain execution behavior. Original `command_handlers={...}` mappings remain supported without metadata. Default help uses the effective registry; explicitly supplied help handlers retain their dispatch priority. Handler exceptions propagate through the frontend's normal cleanup; handlers own their service-specific diagnostics.

[Built-in features](features/README.md) register configuration, recovery, improvement, and cancellation outside the input loop. The frontend owns stdin and lending/restoring the menu display. A handler needing a menu can use `frontend.menu_scope()` while the main loop is dispatching it; do not start a second reader. Operations that change work or runtimes must call Application's public APIs so its state checks remain authoritative.

## Bind optional host operations

[TerminalBindings](bindings.py) names queueing, waiting, recovery, configuration readers, history, authorization, and notification operations. `from_session()` provides the default adapter for existing embedding hosts; `TerminalFrontend(bindings=...)` permits explicit binding. Compatibility discovery is confined to this adapter. Live readers follow runtime replacement.

`ImprovementClients` independently injects search, candidate review, task materials, and activation clients. Pass it as `improvement_clients=` when these capabilities come from different objects. The improvement menu offers the supplied workflow and review capabilities. Corrections are available through the host task-material API, not a terminal form. `improvement_frontend()` returns the current menu view; `show_history()` and `show_notifications()` expose observation without granting execution.

`FormIO` in [forms.py](features/configuration/forms.py) supplies menu selection, input, rendering, and staging callbacks. Forms do not receive a configuration frontend or use its private methods. The host model service still owns validation and persistence. No new environment variables or independent lifecycle state.

## Modules

| File / package | Responsibility |
|---|---|
| [frontend.py](frontend.py) | Single input owner, menu lending, and command dispatch |
| [bindings.py](bindings.py), [commands.py](commands.py) | Optional host capabilities and asynchronous command registration |
| [notifications.py](notifications.py) | Deduplicated improvement progress and candidate notices |
| [I/O](io/README.md) | Line/key readers, live terminal control, menu primitives, and shared safe text utilities |
| [Rendering](rendering/README.md) | Events, history, Markdown, welcome, and branding |
| [Features](features/README.md) | Configuration, restoration, and improvement; each package keeps its handler and menu together |

I/O does not import rendering or feature modules. Rendering consumes I/O primitives and frontend contracts. Feature packages consume contracts, bindings, and I/O/rendering interfaces; they do not import one another. TerminalFrontend and feature assembly compose them through callbacks.

```bash
.venv/bin/python -m unittest discover -s tests/interactive -t . -v
```

Waiting/retry/timeout activity includes request and adapter attempt identities. Timeout text describes an exceeded waiting deadline; it does not assert server overload. `/status` prefers the latest prepared-input estimate for context usage, with a same-model Provider receipt as fallback. A 20-cell ASCII occupancy bar accompanies the percentage, source and last-request scope; it works without ANSI or color. The bar stops at full, while percentages above 100% remain visible. Reported input receipts can exclude cached input according to the Provider convention. Estimates do not guarantee tokenizer accuracy and can be stale after new input. Missing measurements or configured capacity display `unknown` without a bar. Compactions count committed reductions across the session, including restored records; budget checks and cancelled proposals do not increment the count. The `messages` field counts original committed Session messages, including user, assistant and tool results, even while work is running. Context reduction does not reduce this conversation total; metadata and streamed fragments are excluded. See [Interactive status semantics](../README.md#state-and-events) for the in-memory embedding fallback.

## Respond to permission requests

The real interactive terminal presents the tool, operation, canonical targets, command/code when applicable, and the scope of session approval. The ANSI permission frame shows English options with a moving `❯` and a highlighted current row; NO_COLOR keeps the marker. Up/Down moves the selection and Enter confirms the selected option. The initial selection is Allow once. Numeric shortcuts **1**, **2**, and **3** choose Allow once, the displayed scope for this runtime session, and Deny respectively; Esc also denies. The menu clears after resolution. Ctrl+C cancels the run.

The existing input reader routes approval keys; no second stdin reader is started. Ordinary non-ANSI TTY input uses numbered choices followed by Enter. Redirected input does not enable confirmations and therefore cannot silently approve local execution or external file operations. `/permissions clear` revokes remembered approvals while normal command input is available; use Esc to deny an active prompt.

Local execution approval is not a sandbox. Approved Bash or Python retains current-user filesystem/network access. The terminal shows this boundary beside execution confirmation. File directory approval is separate from local execution approval.

Optional [MCP services](../../lab/mcp/README.md) require a separate local-process
startup review before ordinary input starts or while configuration input is lent.
The review shows command, arguments, directory and injected variable names, never
resolved secret values. Redirected startup is denied. External tool calls use the
normal approval frame with grants scoped to one tool and frozen runtime identity.
`/lab` shows tool services separately from the file/Bash execution backend.

## Inspect tool execution

Tool calls show a readable action and operation arguments, then an explicit result
status and elapsed time when available. Labels and call descriptions come from the
tool declarations; the terminal does not interpret individual tools. Errors and
cancelled calls have distinct markers, including when no success hook ran.

Live tool output and final summaries have display bounds. Omitted live output has
an explicit marker. These bounds do not alter stored messages or model context.
