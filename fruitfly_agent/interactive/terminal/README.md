# Terminal

[Up: Interactive](../README.md)

Use FruitFlyAgent through stdin/stdout, menus, and live events. Application owns sessions and work; this frontend handles input and display.

## Daily use

| Need | Action |
|---|---|
| Start | Run `python -m fruitfly_agent`; choose **Start new session**. |
| Configure | `/config`; save choices for a new session. |
| Select a prompt | **Configure → Base prompt**; preview and confirm. |
| Inspect activity | `/status` |
| Cancel active work | `/cancel` |
| Review live details | `/trace` |
| Search or review candidates | `/optimize [DIRECTION]` |
| Run external evaluation while idle | `/eval` |

POSIX ANSI terminals support live input, history, cancellation, and bracketed paste. Redirected input uses line-based fallback. Display limits do not alter model context or stored messages. `NO_COLOR` and terminal capabilities affect rendering.

## Configure

| Menu | Behavior |
|---|---|
| Model / Base prompt | Select the model and prompt for the next session. |
| Context Manager, Tools, Environment, Optimization | Enable responsibilities and choose algorithms in-place. |
| Algorithm selector | Expand on the current row, including single-algorithm groups. |
| Detailed parameters | Edit harness YAML; no parameter submenu. |
| Prompt results | Current configuration/profile's latest task-scoped prompt candidates, plus built-ins and current selection |

Expanding a prompt group does not change configuration. Choosing a prompt opens a full preview and confirmation. Active and resumed sessions retain their manifest. See [Configuration](../../../CONFIGURATION.md).

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
| [live.py](live.py), [input.py](input.py) | TTY editing and live input |
| [menu.py](menu.py), [screen.py](screen.py) | Navigation and temporary menu display |
| [configuration.py](configuration.py), [resume.py](resume.py), [evaluation.py](evaluation.py) | Service-driven menus |
| [markdown.py](markdown.py), [text.py](text.py) | Safe content rendering |
| [welcome.py](welcome.py), [branding.py](branding.py) | Welcome and identity display |

```bash
.venv/bin/python -m unittest tests.interactive.test_terminal tests.interactive.test_line_editor tests.interactive.test_menu -v
```
