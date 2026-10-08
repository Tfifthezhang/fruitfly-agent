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
| Search or review candidates | `/optimize [DIRECTION]` |
| Run external evaluation while idle | `/eval` |

POSIX ANSI terminals support live input, history, cancellation, and bracketed paste. Non-ANSI POSIX TTY input uses a stoppable canonical reader and handles SIGINT while a run is waiting. Redirected input uses sequential line-based fallback and cannot consume `/cancel` during a run. Display limits do not alter model context or stored messages. `NO_COLOR` and terminal capabilities affect rendering.

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
| `mechanisms · context-manager`, `mechanisms · tools`, `mechanisms · environment`, `mechanisms · optimization` | Enable responsibilities and choose algorithms in-place. |
| Algorithm selector | Expand on the current row, including single-algorithm groups. |
| Detailed parameters | Edit harness YAML; no parameter submenu. |
| Prompt results | Current configuration/profile's latest task-scoped prompt candidates, plus built-ins and current selection |

Expanding a prompt group does not change configuration. Choosing a prompt opens a full preview and confirmation. Active and resumed sessions retain their manifest. See [Configuration](../../../CONFIGURATION.md).

Selecting a service replaces the choice menu with one field per screen. Each field shows the selected service, step count, its purpose, and any default. Input frames use the field name; normal conversation frames keep their prompt label. Official and custom services have separate address instructions. `models.<name>` is the menu name; `model` is the service's exact identifier. Other fields use their YAML keys.

The `capabilities` page renders host-provided booleans as checkboxes with defaults. Space or Enter toggles the selected capability; Continue confirms. Choices limited to one value remain fixed and explain the requirement. Checked values are staged as `true`, unchecked values as `false`; cancel discards the page. The host remains responsible for capability validation.

Model forms accept `/cancel` or EOF without staging. Review includes the selected service and defaults to Cancel. API key input disables TTY echo and bypasses readline/history; redirected input is read directly without writing its value to output. The host validates and saves settings; the terminal performs no Provider requests or filesystem configuration writes.

## Optimize and review

| Action | Behavior |
|---|---|
| Start optimization | Choose a pack, direction, and explicit cost confirmation. |
| Save a failed task | Supply self-contained input and real acceptance criteria; confirm train-only saving. |
| Review candidates | Overview, evaluation, usage, changes, original/candidate text, scope, and evidence |
| `n` / `p` | Change section; fallback uses `next` / `previous`. |
| PageUp / PageDown | Page long content; fallback uses `pageup` / `pagedown`. |
| Save for later | Set next-session default. |
| Use for a new session | Confirm activation of a new empty session. |

Confirmation defaults to cancel; review actions default to Back. Arrow keys only move selection; Enter performs it. Progress updates appear at most every 0.5 seconds while waiting for normal ANSI input and only when changed. Non-ANSI input uses `/status` or input boundaries. Progress measures the current batch, not total search completion.

See [Optimization](../../lab/optimization/README.md) for model budgets and [Task packs](../../lab/optimization/TASK_PACKS.md) for acceptance rules. Candidates do not guarantee improvement.

## Evaluation

| Step / control | Behavior |
|---|---|
| Selection | Mode → benchmark → resource variant → optional mechanism → cost confirmation |
| Esc / `back` / `b` | Return one level, retaining selections. |
| `q` | Return to the conversation. |
| **Run** | Explicitly start a separate evaluation process. |
| Display | Condition, artifacts, Agent activity, task completion, and complete setup/runner diagnostics |

The frontend waits for evaluation to return; ordinary chat and the optimization cancellation panel are not available during it. Five-second job snapshots do not show precise image download/build progress. Model requests and containers may incur costs. Full logs and event archives belong to [Eval](../../../eval/README.md).

## Files

| Files | Responsibility |
|---|---|
| [frontend.py](frontend.py), [renderer.py](renderer.py) | Input routing and event display |
| [history.py](history.py) | Static canonical conversation display, separate from live events |
| [live.py](live.py), [input.py](input.py) | TTY editing and live input |
| [menu.py](menu.py), [screen.py](screen.py) | Navigation and temporary menu display |
| [configuration.py](configuration.py), [resume.py](resume.py), [evaluation.py](evaluation.py) | Service-driven menus |
| [model_setup.py](model_setup.py) | Generic model form, review, and secret input with echo restoration |
| [optimization.py](optimization.py) | Search confirmation, candidate review, and corrected-task menus with injected services |
| [markdown.py](markdown.py), [text.py](text.py) | Safe content rendering |
| [welcome.py](welcome.py), [branding.py](branding.py) | Welcome and identity display |

```bash
.venv/bin/python -m unittest discover -s tests/interactive -t . -v
```

Waiting/retry/timeout activity includes request and adapter attempt identities. Timeout text describes an exceeded waiting deadline; it does not assert server overload. `/status` prefers the latest prepared-input estimate for context usage, with a same-model Provider receipt as fallback. The line labels the source and last-request scope. Reported input receipts can exclude cached input according to the Provider convention. Estimates do not guarantee tokenizer accuracy and can be stale after new input. Missing measurements or configured capacity display `unknown`. Compactions count committed reductions across the session, including restored records; budget checks and cancelled proposals do not increment the count.

## Respond to permission requests

The real interactive terminal presents the tool, operation, canonical targets, command/code when applicable, and the scope of session approval. Choose **1 / Enter** to allow once, **2** to allow the displayed scope for this runtime session, or **3 / Esc** to deny. The ANSI editor also supports Up/Down then Enter. Ctrl+C cancels the run.

The existing input reader routes approval keys; no second stdin reader is started. Ordinary non-ANSI TTY input uses numbered choices followed by Enter. Redirected input does not enable confirmations and therefore cannot silently approve local execution or external file operations. `/permissions clear` revokes remembered approvals while normal command input is available; use Esc to deny an active prompt.

Local execution approval is not a sandbox. Approved Bash or Python retains current-user filesystem/network access. The terminal shows this boundary beside execution confirmation. File directory approval is separate from local execution approval.
