# Terminal

[Up: Interactive](../README.md)

Use FruitFlyAgent through stdin/stdout, menus, and live events. Application owns sessions and work; this frontend handles input and display.

## Daily use

| Need | Action |
|---|---|
| Start | Run `python -m fruitfly_agent`; choose **Start new session**. |
| Configure | `/config`; save choices for a new session. |
| Select a prompt | **Configure → prompt**; preview and confirm. |
| Inspect activity | `/status`: model, prompt, workspace, session, message count, state, queue, pending candidates, context usage percentage, and session compaction count. |
| Cancel active work | `/cancel` or the first Ctrl+C; clear pending Application input. |
| Exit | `/exit`, `/quit`, or a second Ctrl+C within three seconds; drain cancelled work before resource cleanup. |
| Clear a draft | First Ctrl+C while idle; normal submitted input resets the double-press interval. |
| Restore a conversation | `/resume` to choose a session; `/resume PATH` to switch directly. |
| Review live details | `/trace` |
| Search or review candidates | `/improvement [DIRECTION]` |

POSIX ANSI terminals support live input, history, cancellation, and bracketed paste. Non-ANSI POSIX TTY input uses a stoppable canonical reader and handles SIGINT while a run is waiting. Redirected input uses sequential line-based fallback and cannot consume `/cancel` during a run. Display limits do not alter model context or stored messages. `NO_COLOR` and terminal capabilities affect rendering.

The editable input area has a contrasting background, an emphasized `❯` prefix, and vertical spacing without full-width borders. Submitted inputs retain an emphasized prefix and blank lines, without background fill. The input uses a neutral gray background and the terminal’s default text color, with light/dark hints and capability fallbacks described in [I/O](io/README.md); `NO_COLOR` keeps the text and spacing. Terminal resizing refreshes the editable layout while retaining the draft and cursor. Completed transcript lines remain in terminal scrollback.

Live reasoning text is hidden. The existing activity display indicates reasoning, answer reception, and tool execution; redirected output keeps brief activity milestones without animation. Reasoning summaries are also hidden. This presentation policy adds no model requests and does not change reasoning usage. Ordinary assistant text and bounded tool output remain visible.

## Restore a conversation

After successful `/resume` or interactive startup with `--resume`, the terminal appends the original conversation in chronological order, followed by an end marker and the normal input prompt. User and assistant text is complete; ANSI terminals format assistant Markdown. Use terminal scrollback to review earlier turns. Existing scrollback is retained, and menus do not replay history.

Tool calls show names without arguments. Tool results show at most 800 characters per message and explicitly mark omitted output. Images show attachment/media-type markers; reasoning shows an omission marker. Internal context summaries and transient activity events are not replayed. History display makes no model requests, executes no tools, and writes no messages. Context reduction may still affect the context sent to the model.

Cancelled or failed restoration keeps the current session and does not display the target history. Embedding hosts can optionally expose `conversation()` using the [Interactive views](../README.md#state-and-events); existing terminal hosts without it continue to work. A single-task CLI run with `--resume` continues saved context without printing the historical conversation.

## Configure

| Menu | Behavior |
|---|---|
| `model` / `prompt` | Select the model and prompt for the next session. |
| Add model… | Collect host-provided service fields, hidden API key, and review; stage until configuration save. Opens on first startup when no models exist. |
| Set API key… | Stage a missing credential for the selected model; the menu shows only set/missing status. |
| Tools → Set up… | Select a web service and optional key variable, enter a hidden API key, and stage until configuration save. Direct fetch skips key input. |
| Context, Tools, Environment | One readable row per mechanism; Enter expands algorithm choices and descriptions, Details reveals paths/configuration locations, Space enables/disables. |
| Context sections | Augmentation groups Skills, Memory, Knowledge and HTTP; externalization and reduction remain separate sections on the same page. |
| Algorithm selector | Multiple implementations use inline radio choices; sole implementations expose a description with expandable Details. |
| User inputs | Edit declared paths, initial text and endpoints with visible input; tune internal parameters in the displayed YAML location. |
| Prompt results | Current configuration/profile's latest task-scoped prompt candidates, plus built-ins and current selection |

Expanding a prompt group does not change configuration. Choosing a prompt opens a full preview and confirmation. Active and resumed sessions retain their manifest. See [Configuration](../../../CONFIGURATION.md).

Selecting a service replaces the choice menu with one field per screen. Each field shows the selected service, step count, its purpose, and any default. Field prompts use the field name; conversation input uses `❯`. Official and custom services have separate address instructions. `models.<name>` is the menu name; `model` is the service's exact identifier. Other fields use their YAML keys.

The `capabilities` page renders host-provided booleans as checkboxes with defaults. Space or Enter toggles the selected capability; Continue confirms. Choices limited to one value remain fixed and explain the requirement. Checked values are staged as `true`, unchecked values as `false`; cancel discards the page. The host remains responsible for capability validation.

Model forms accept `/cancel` or EOF without staging. Review includes the selected service and defaults to Cancel. API key input disables TTY echo and bypasses readline/history; redirected input is read directly without writing its value to output. The host validates and saves settings; the terminal performs no Provider requests or filesystem configuration writes.

Mechanism forms refresh credential requirements from pending non-secret field
values before hidden input. Switching a service or key variable changes the
binding within that form. `/clear` clears an ordinary field; required-field
validation still applies. Hidden input and review reuse the model form's echo,
history, cancellation and staging behavior. The host owns secret-file writes.

## Improve against a task set

`/improvement [DIRECTION]` opens Target, Task, Budget and Evaluation on one panel. Expand Target, choose an object, then its algorithm below it. H/S/I are section labels. Algorithms show concise descriptions; Details reveals implementation/guide paths and YAML locations. Optional Search guidance remains editable inline; internal tuning uses the configuration location in Details. Task expands saved/benchmark sources and material fields; Budget expands limits; Evaluation exposes scoring, acceptance and preview details. New drafts require explicit target/algorithm selection. Compatible values survive changes; missing inputs remain visible. Field editing retains the panel and focus while displaying live text and validation hints.

| Action | Behavior |
|---|---|
| Start improvement | Fresh preview and one confirmation, defaulting to Cancel; model work may incur charges |
| Budget | Edit typed method-declared limits without JSON |
| Target | Choose an object, then a compatible algorithm with description and paths; edit optional Search guidance |
| Task / Evaluation | Choose materials and inspect scoring/acceptance |
| Return to chat while running | Continue Application-owned work; inspect `/status`, `/cancel`, or Results and history |
| Results and history | Inspect every submitted run, including empty, failed and cancelled experiments |
| Review candidate | Assessment, comparison, usage, changes, original/candidate text, scope and evidence |
| Set as next-session default | Confirm a saved configuration change without replacing the active session |
| Set default and start a new session | Confirm the default change and open an empty session |

Back/Esc cancels active field input, then collapses a section, then returns to chat. Draft fields remain intact. `q` exits menu mode and is literal text during field input. Cyan focus and green enabled/selected markers remain distinct; Modified/warnings use yellow and errors use red. Section titles and indentation express hierarchy. Raw-key menus omit row numbers; line fallback retains them. `NO_COLOR` preserves symbols and text. Confirmation always starts with Cancel selected. Detail actions default to Back; `n`/`p` switch sections, PageUp/PageDown page text. Numbered fallback accepts next/previous and pageup/pagedown. Cancellation and outcomes remain visible after restoring chat. Candidates are already stored and do not guarantee improvement.

Saved tasks and benchmarks use the same running/result flow. Raw TTY input polls through the existing reader to refresh progress and offer return/cancel actions. Redirected/non-polling input waits for completion and cannot consume `/cancel` during the wait. Progress measures the current batch, not overall completion. Results expose the stop reason and measured evidence even when no candidate is published. See the [feature guide](features/improvement/README.md).

## Use benchmark tasks

Set **Task** to a benchmark/task-set row, then choose **Start improvement** and confirm. One Application job prepares/freeze tasks and runs baseline, failure processing, candidate search, original-task comparisons and independent confirmation. No separate initial evaluation or enable switch is required. Full original-task output and logs remain observable; missing execution capabilities/preflight checks explain why a source is unavailable.

Benchmark sources are optional. Saved packages and candidates remain available without Eval. Standalone reports use the [Eval CLI](../../../eval/README.md). Containers, downloads and model calls may incur cost. Current source choices use five tasks and a 3/1/1 split, suitable for examining control flow rather than establishing general quality.

## Register a command

`TerminalFrontend(command_handlers={...})` accepts synchronous or asynchronous handlers. Each receives an `InteractiveCommand` and returns a `CommandResult`. The frontend writes its result and handles exit; handlers capture only the service operations they need. Registered terminal commands run before the frontend-neutral CommandRouter fallback.

```python
from fruitfly_agent.interactive.interaction.commands import CommandResult
from fruitfly_agent.interactive.terminal import TerminalFrontend

# application is an already constructed host. This example makes no model request.
async def describe(command):
    return CommandResult(text=f"Runtime: {application.runtime_manifest['digest']}\n")

frontend = TerminalFrontend(application, command_handlers={"describe": describe})
# await frontend.run() starts terminal input.
```

Names are lowercase, path-free tokens. Duplicate registration raises an error. `frontend.commands.register(name, handler, replace=True)` explicitly replaces a registered terminal handler. `/quit` is parsed as `/exit`. Custom commands are not added to `/help` automatically. Handler exceptions propagate through the frontend's normal cleanup; handlers own their service-specific diagnostics.

[Built-in features](features/README.md) register configuration, recovery, improvement, and cancellation outside the input loop. The frontend owns stdin and lending/restoring the menu display. A handler needing a menu can use `frontend.menu_scope()` while the main loop is dispatching it; do not start a second reader. Operations that change work or runtimes must call Application's public APIs so its state checks remain authoritative.

## Bind optional host operations

[TerminalBindings](bindings.py) names queueing, waiting, recovery, configuration readers, history, authorization, and notification operations. `from_session()` provides the default adapter for existing embedding hosts; `TerminalFrontend(bindings=...)` permits explicit binding. Compatibility discovery is confined to this adapter. Live readers follow runtime replacement.

`ImprovementClients` independently injects search, candidate review, task materials, and activation clients. Pass it as `improvement_clients=` when these capabilities come from different objects. The improvement menu offers only the supplied capabilities. Material-only hosts can save corrections without offering search afterward. `improvement_frontend()` returns the current menu view; `show_history()` and `show_notifications()` expose observation without granting execution.

`ModelFormIO` in [model_setup.py](features/configuration/model_setup.py) supplies menu selection, input, rendering, and staging callbacks. Forms do not receive a configuration frontend or use its private methods. The host model service still owns validation and persistence. No new environment variables or independent lifecycle state.

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

Waiting/retry/timeout activity includes request and adapter attempt identities. Timeout text describes an exceeded waiting deadline; it does not assert server overload. `/status` prefers the latest prepared-input estimate for context usage, with a same-model Provider receipt as fallback. The line labels the source and last-request scope. Reported input receipts can exclude cached input according to the Provider convention. Estimates do not guarantee tokenizer accuracy and can be stale after new input. Missing measurements or configured capacity display `unknown`. Compactions count committed reductions across the session, including restored records; budget checks and cancelled proposals do not increment the count.

## Respond to permission requests

The real interactive terminal presents the tool, operation, canonical targets, command/code when applicable, and the scope of session approval. The ANSI permission frame shows English options with a moving `❯` and a highlighted current row; NO_COLOR keeps the marker. Up/Down moves the selection and Enter confirms the selected option. The initial selection is Allow once. Numeric shortcuts **1**, **2**, and **3** choose Allow once, the displayed scope for this runtime session, and Deny respectively; Esc also denies. The menu clears after resolution. Ctrl+C cancels the run.

The existing input reader routes approval keys; no second stdin reader is started. Ordinary non-ANSI TTY input uses numbered choices followed by Enter. Redirected input does not enable confirmations and therefore cannot silently approve local execution or external file operations. `/permissions clear` revokes remembered approvals while normal command input is available; use Esc to deny an active prompt.

Local execution approval is not a sandbox. Approved Bash or Python retains current-user filesystem/network access. The terminal shows this boundary beside execution confirmation. File directory approval is separate from local execution approval.

## Inspect tool execution

Tool calls show a readable action and operation arguments, then an explicit result
status and elapsed time when available. Labels and call descriptions come from the
tool declarations; the terminal does not interpret individual tools. Errors and
cancelled calls have distinct markers, including when no success hook ran.

Use `/tools` to list completed results in the current host's retained event window,
then `/tools CALL_ID` for the retained output and bounded argument summary. Reused
call IDs resolve to the latest retained completion. The view does not invoke tools,
make model requests, or start another input reader. It follows runtime replacement
through the optional `TerminalBindings.trace` callback. Hosts without that reader
report that inspection is unavailable. This is not a persistent execution archive;
event eviction and tool-side truncation limit what can be inspected.
