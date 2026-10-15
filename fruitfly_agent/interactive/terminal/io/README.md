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

The live editor uses a background-filled input area with a bold `❯` prefix and one padding row above and below. It keeps full-width borders out of the transcript and creates a text/cursor/history-navigation buffer for each submission. Its existing reader polls terminal size while idle; `InlineTerminalDisplay.refresh()` redraws only when dimensions change. Resize cleanup accounts for wrapped old rows before drawing the new layout, without replaying committed history. Plain readline prompts are the default; embeddings may explicitly request framed forms. Control keys and escape sequences edit that buffer; permission choices return a request reply without editing it. Submission history belongs to the editor, while an unsubmitted draft belongs to the current read. Generic `navigate_menu` handles wrapping and rejects numbered choices outside the displayed rows.

`InlineTerminalDisplay.set_choices(labels, selected)` replaces the input area with transient choice rows. A `❯` marks the current row; color-enabled terminals also highlight it. Arrow keys move the selection, Enter submits it, numeric shortcuts select directly, and Esc denies permission. The permission menu uses the host-provided session scope, respects terminal width/height and NO_COLOR, and clears on resolution. Choice redraws do not append menu rows to conversation history or clear the full screen. Non-ANSI readers retain numbered line input.

`input_styles()` in [text.py](text.py) uses a neutral gray background, the terminal’s default foreground, and a bold prompt. This approximates the low-contrast input surface in [Codex CLI](https://github.com/openai/codex/blob/main/codex-rs/tui/src/style.rs), rather than measuring and blending the actual terminal background. `COLORFGBG` backgrounds 7 and 15 select light gray; missing or other hints select dark gray. True-color terminals use RGB gray 242 or 48; 256-color terminals use palette entry 255 or 236. Basic-color terminals use ANSI white or bright black, whose appearance depends on the terminal palette. There is no transparency or terminal background query. Reverse video is never used. Cursor colors are not changed. Only editable rows receive the fill; each row resets its style before other output. Submitted history keeps its native background and foreground with a bold prefix. `NO_COLOR` disables fill and accents while retaining the prompt and spacing.

TERM, COLORTERM, COLORFGBG, NO_COLOR, locale, and stream capabilities affect display/input behavior. POSIX terminal control is required for live/raw input. Redirected streams use a deterministic fallback. Cell widths are approximations and display limits do not alter model context or persisted data. No model calls or configuration writes.

```bash
.venv/bin/python -m unittest tests.interactive.test_input_emphasis tests.interactive.test_line_editor tests.interactive.test_menu tests.workflows.test_terminal_interrupt -v
```

Checks use local PTYs and isolated streams.
