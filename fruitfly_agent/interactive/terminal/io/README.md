# Terminal I/O

[Up: Terminal](../README.md)

Provide replaceable input readers and terminal control primitives. This layer has no knowledge of Application state, feature commands, or model operations.

| File | Responsibility |
|---|---|
| [input.py](input.py) | LineEditor, redirected/readline/canonical readers, and field input |
| [live.py](live.py) | InlineTerminalDisplay, concurrent editing, bracketed paste, and interruption |
| [menu.py](menu.py) | MenuInput, key decoding, navigation, generic rows, and menu display |
| [screen.py](screen.py) | transient_screen lending/restoration |
| [text.py](text.py) | TTY/color checks, safe terminal text, cell width, and truncation |

TerminalFrontend owns the active input loop. Features borrow the supplied reader/menu scope; they must not start a second background stdin reader. TTY mode and screen restoration run on every exit. Rendering consumes these primitives; I/O never imports rendering or feature modules.

TERM, NO_COLOR, locale, and stream capabilities affect display/input behavior. POSIX terminal control is required for live/raw input. Redirected streams use a deterministic fallback. Cell widths are approximations and display limits do not alter model context or persisted data. No model calls or configuration writes.

```bash
.venv/bin/python -m unittest tests.interactive.test_line_editor tests.interactive.test_menu tests.workflows.test_terminal_interrupt -v
```

Checks use local PTYs and isolated streams.
