# Terminal I/O

[Up: Terminal](../README.md)

Provide replaceable input readers and terminal control primitives. This layer has no knowledge of Application state, feature commands, or model operations.

| File | Responsibility |
|---|---|
| [input.py](input.py) | LineEditor, redirected/readline/canonical readers, and field input |
| [live.py](live.py) | InlineTerminalDisplay, owned/inline display modes, concurrent editing, bracketed paste, and interruption |
| [transcript.py](transcript.py) | Source-backed display records, injected formatting, cached layout and scroll anchors |
| [menu.py](menu.py) | MenuInput, key decoding, navigation, generic rows, and menu display |
| [screen.py](screen.py) | transient_screen lending/restoration |
| [text.py](text.py) | TTY/color checks, safe terminal text, cell width, content width, wrapping and truncation |

TerminalFrontend owns the active input loop. Features borrow the supplied reader/menu scope; they must not start a second background stdin reader. TTY mode and screen restoration run on every exit. Raw menu input additionally offers bounded `poll_event(timeout)` reads through the same owner, preserving queued keys and restoring blocking/terminal modes. Polling restores modes without waiting for output to drain. Rendering consumes these primitives; I/O never imports rendering or feature modules.

`MenuRow` carries section titles, indentation, state markers, draft-change flags and labeled path `references`. References wrap without ellipsis, use reduced emphasis, consume no selection indices and count toward viewport scrolling. Large reference blocks use `reference_page`; the renderer reports its clamped `reference_page` so owners can route PageUp/PageDown through their existing input loop. Numbered fallback shows complete references. Section titles consume no input indices. Raw-key ANSI menus use a `❯` focus without row numbers; line-based input retains numbered actions, including on ANSI output. Long menus scroll to the focused row and repeat the current section title. `TerminalMenuRenderer.begin_input` retains the menu and focuses the edited field while showing input rules.

Focus uses cyan emphasis and the neutral `input_styles` background; enabled/selected markers use green, Modified/warnings use yellow, and errors use red. Group headings use blue/bold; option labels use bold. Descriptions, references, page subtitles and navigation hints use reduced emphasis. Font size follows terminal settings; the renderer does not resize individual rows. Symbols and text preserve all states without color. Existing light/dark, basic/256/true-color and `NO_COLOR` fallbacks apply. `NO_COLOR` emits no SGR styling.

`field_prompt` and `parse_field_value` interpret generic field metadata; host validation remains authoritative. `read_field_line(editor, label)` borrows the existing reader with a visible display and separate field history while chat is suspended. Submission, EOF, Esc and interruption restore display, history and terminal mode. Typing/cursor edits remain visible with terminal echo disabled. `q`, spaces and digits are literal text during input. Readline/stream readers retain labeled fallback; `/cancel` belongs to the form. Secret fields retain their separate echo-suppressed reader.

The live editor uses a background-filled input area with a bold `❯` prefix and one padding row above and below. It keeps full-width borders out of the transcript and creates a text/cursor/history-navigation buffer for each submission. Its existing reader polls terminal size while idle; `InlineTerminalDisplay.refresh()` redraws on dimension changes. The built-in frontend requests `fullscreen=True`: alternate-screen output uses original display sources to reflow history and input. Default embedding construction remains append-only and redraws its live tail; it cannot reflow terminal-owned scrollback. Plain readline prompts are the default; embeddings may explicitly request framed forms. Control keys and escape sequences edit that buffer; permission choices return a request reply without editing it. Submission history belongs to the editor, while an unsubmitted draft belongs to the current read. Generic `navigate_menu` handles wrapping and rejects numbered choices outside the displayed rows.

`InlineTerminalDisplay.set_choices(labels, selected)` replaces the input area with transient choice rows. A `❯` marks the current row; color-enabled terminals also highlight it. Arrow keys move the selection, Enter submits it, numeric shortcuts select directly, and Esc denies permission. The permission menu uses the host-provided session scope, respects terminal width/height and NO_COLOR, and clears on resolution. Choice redraws do not append menu rows to conversation history. Non-ANSI readers retain numbered line input.

`input_styles()` in [text.py](text.py) uses a neutral gray background, the terminal’s default foreground, and a bold prompt. This approximates the low-contrast input surface in [Codex CLI](https://github.com/openai/codex/blob/main/codex-rs/tui/src/style.rs), rather than measuring and blending the actual terminal background. `COLORFGBG` backgrounds 7 and 15 select light gray; missing or other hints select dark gray. True-color terminals use RGB gray 242 or 48; 256-color terminals use palette entry 255 or 236. Basic-color terminals use ANSI white or bright black, whose appearance depends on the terminal palette. There is no transparency or terminal background query. Reverse video is never used. Cursor colors are not changed. Only editable rows receive the fill; each row resets its style before other output. Submitted history keeps its native background and foreground with a bold prefix. `NO_COLOR` disables fill and accents while retaining the prompt and spacing.

TERM, COLORTERM, COLORFGBG, NO_COLOR, locale, and stream capabilities affect display/input behavior. POSIX terminal control is required for live/raw input. Redirected streams use a deterministic fallback. Cell widths are approximations and display limits do not alter model context or persisted data. No model calls or configuration writes.

```bash
.venv/bin/python -m unittest tests.interactive.test_input_emphasis tests.interactive.test_line_editor tests.interactive.test_menu tests.workflows.test_terminal_interrupt -v
```

Checks use local PTYs and isolated streams.

`DisplayTranscript` accepts plain fragments or `update(source, formatter,
complete=...)` records. Formatting callbacks and visual wrapping are injected;
the module knows no Markdown, message roles, Session files or lifecycle state.
Cached layouts are invalidated by changed source or width. PageUp/PageDown and
SGR mouse-wheel input move a display-only anchor; Ctrl+End resumes bottom-follow.
Anchors use a record and visible-character offset, so appended text does not pull
a reader to the bottom. Width-dependent decorations, including table borders,
can shift the exact anchored row on resize. Draft text and cursor stay independent.

Fullscreen suspension disables mouse reporting and bracketed paste and restores
the shell screen. Reactivation restores retained display records, including after
menus; output received while suspended is buffered. The cache lasts for the
frontend's lifetime and is not persisted. Exit does not copy the alternate-screen
transcript into shell scrollback; use Session recovery to review saved messages.
