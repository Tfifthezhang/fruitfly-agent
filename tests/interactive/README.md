# Interactive Tests

[Up: Tests](../README.md)

Verify Application state/lifecycle, resource cleanup, events, menus, commands, and terminal I/O.

| Files | Protects |
|---|---|
| `test_authorization.py` | Single/directory/session approval, stale replies, serialization, timeout, and cancellation |
| `test_run_control.py / test_context_status.py` | Quiet cancellation, complete interrupted tool associations, queue/retirement bounds, compact context usage display, separate measurements, and restored committed-compaction counts |
| `test_terminal.py` | Commands, concurrent input, resume, and optimization dispatch |
| `test_conversation.py` | Immutable original history after reduction, safe content projection, and static display bounds |
| `test_terminal_configuration.py / test_menu.py` | Configuration drafts, startup confirmation, and generic menu navigation |
| `test_terminal_renderer.py / test_markdown.py / test_welcome.py` | Event presentation, output bounds, ANSI handling, and layouts |
| `test_evaluation.py` | Generic Eval menu and complete diagnostic display |
| `test_line_editor.py` | PTY input, explicit TERM, redirected fallback, and model-key echo suppression/restoration |

Local PTYs and fake models. Assembly/CLI belong to Run; complete multi-module paths belong to Workflows.

Finite input and TTY streams come from [terminal support](../support/terminal.py). Configuration menus use the shared [controller substitutes](../support/configuration.py); their public entry points drive dropdown and confirmation checks.

```bash
.venv/bin/python -m unittest discover -s tests/interactive -t . -v
```
