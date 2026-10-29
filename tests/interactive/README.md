# Interactive Tests

[Up: Tests](../README.md)

Verify Application state/lifecycle, resource cleanup, events, menus, commands, and terminal I/O.

| Files | Protects |
|---|---|
| `test_viewport.py` | Optional fullscreen embedding reflow, source/cache preservation, scroll anchors, drafts and menu restoration |
| `test_authorization.py` | Single/directory/session approval, stale replies, serialization, timeout, and cancellation |
| `test_run_control.py / test_context_status.py` | Quiet cancellation, complete interrupted tool associations, queue/retirement bounds, live canonical-message counts across compaction/recovery, context usage bars, separate measurements, and restored committed-compaction counts |
| `test_extensions.py` | Independent service injection, async commands, explicit host bindings, menu capability composition, cleanup, and improvement completion/cancellation races |
| `test_lab.py` | Single-snapshot runtime inspection, unknown metadata, capability availability, generic title blocks, plain-output fallback and narrow-window wrapping |
| `test_environment_display.py` | Distinct host/execution locations, complete narrow-window and IPv6 addresses, plain output and unknown/custom backend metadata |
| `test_native_display.py` | Buffered assistant/tool output, retained unfinished previews and drafts while a menu borrows the main-screen terminal |
| `test_tool_presentation.py` | Tool-owned descriptions, fallback/isolation, serialized outcomes, parallel cancellation, legacy events, bounded output and rejection of the removed tool-inspection command |
| `test_terminal.py` | Commands, concurrent input, resume, and improvement dispatch |
| `test_conversation.py` | Immutable original history after reduction, safe content projection, and static display bounds |
| `test_terminal_configuration.py / test_menu.py` | Context phase headings, focused bottom help, single-implementation settings, inline radio choices, stable focus, disabled/required groups, NO_COLOR/light-dark fallback, small-terminal field input, drafts and confirmation |
| `test_terminal_renderer.py / test_markdown.py / test_welcome.py` | Event presentation, output bounds, ANSI handling, and layouts |
| `test_improvement.py / test_improvement_back.py` | Inline target-before-algorithm selection, field focus/current values, compatible budget retention, task revalidation, optional guidance, generic task sources, cost confirmation and cancellation |
| `test_input_emphasis.py` | Dark/light/unknown terminal palettes, NO_COLOR, editor-only fill, and readable submitted/restored input |
| `test_line_editor.py` | PTY resize without keystrokes, visible pre-submission form drafts, cursor/history preservation, form exit/echo restoration, explicit TERM, redirected fallback, and model-key echo suppression/restoration |

Local PTYs and fake models. Assembly/CLI belong to Run; complete multi-module paths belong to Workflows.

Finite input and TTY streams come from [terminal support](../support/terminal.py). Configuration menus use the shared [controller substitutes](../support/configuration.py); their public entry points drive dropdown and confirmation checks.

```bash
.venv/bin/python -m unittest discover -s tests/interactive -t . -v
```
