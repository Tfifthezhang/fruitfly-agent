# Terminal Rendering

[Up: Terminal](../README.md)

Present frontend events, canonical history, Markdown, and status. Rendering observes public views and does not submit work or activate runtimes.

| File / entry | Responsibility |
|---|---|
| [renderer.py](renderer.py): TerminalRenderer | Event display, stream output, history, and display cleanup |
| [tools.py](tools.py) | Shared bounded argument/result summaries and sensitive argument-name redaction |
| [history.py](history.py) | Static canonical conversation rendering |
| [panels.py](panels.py) | Generic read-only command sections, title color blocks and responsive text rows |
| [markdown.py](markdown.py) | Markdown formatting and streamed presentation |
| [welcome.py](welcome.py), [branding.py](branding.py) | Width-based welcome layout, full/small fly marks and project identity |

Use [Contracts](../../contracts/README.md) for event/status/history inputs and [I/O](../io/README.md) for safe text, terminal capabilities, and inline display primitives. This layer never imports features or TerminalFrontend.

`TerminalRenderer.write_command_result` renders an optional structured panel or
the existing text fallback. Panel rendering knows no command names or algorithm
implementations. Category hints select short title background blocks with explicit
foreground/background pairs; body text retains the terminal's ordinary colors.
Unknown categories use a default style. `NO_COLOR`, dumb terminals and redirected
output retain plain section headings and spacing. Narrow terminals stack and wrap
label/value rows, including wide characters; metadata control characters are
escaped. Panels do not create another input reader or change runtime state.

Submitted input is echoed once with an accented bold `❯` prefix, `│` continuation lines, and blank lines before and after it. Bodies keep their ordinary text weight. Resumed user messages have a bold **You** label. No full-row fill or width-dependent border is committed to scrollback; color-disabled output retains the prefixes and spacing. History display preserves full user/assistant text while omitting private reasoning, image bytes, and tool arguments. Tool output has explicit display bounds. TERM/NO_COLOR affect ANSI and color through the I/O layer. These presentation rules do not change canonical messages or model context. No model calls, tools, or persistence effects.

Live reasoning text, including Provider reasoning summaries, is hidden from the transcript. Existing activity events show reasoning status and elapsed time in the inline display; non-interactive output prints activity milestones without animation. Hidden reasoning deltas do not flush Markdown, add blank lines, or reset activity timing. Completion, failure, cancellation, and renderer cleanup clear the activity display. Hiding text does not reduce model reasoning usage or add model requests.

```bash
.venv/bin/python -m unittest tests.interactive.test_lab tests.interactive.test_input_emphasis tests.interactive.test_terminal_renderer tests.interactive.test_markdown tests.interactive.test_welcome tests.interactive.test_conversation -v
```

Tool rows display the tool-owned action description with an explicit running,
completed, failed, cancelled or unknown-outcome marker. Arguments and elapsed time
use reduced emphasis. Tool names remain secondary metadata; rendering has no
branches for concrete tools. Unknown legacy outcomes display Finished rather than
Completed. Descriptions and tool text escape terminal control characters.

Default live tool output shares an 800-character display allowance per run because
the existing partial-output callback does not identify individual calls. Concurrent
starts do not reset that allowance. Final output has a bounded summary; failed and
cancelled results retain a bounded reason preview. Truncated live output has an
explicit omission marker. Display limits do not change stored tool messages or
model context; tool-side truncation still applies.

The built-in ANSI frontend commits completed assistant Markdown, history, welcome
and structured panels to native terminal scrollback. Its streaming presenter
replaces the unfinished tail and appends completed blocks once. Resize redraws
input and the live tail without rewriting committed history or replaying events.
Optional fullscreen sinks advertise `formatted_output`: rendering supplies a
width-dependent formatting callback and I/O owns caching and repainting without
importing Markdown. Those display records are process-local and are not model
context or a substitute for Session storage.

Tables wrap every cell into multiple lines and retain long paths/descriptions.
Very narrow windows use wrapped labeled records. The available width reserves the
terminal's final cell, preventing the right border from wrapping separately.
Paragraph soft breaks reflow as spaces; explicit Markdown hard breaks remain.
Code blocks retain literal lines and receive visual wrapping from I/O. Cell widths
use the shared Unicode approximation; complex emoji sequences may vary by terminal.
Append-only embeddings use the same streaming presenter; redirected streams keep
source Markdown.

Welcome layout measures glyph cell widths. Wide screens pair the full fly with the
large wordmark; medium screens retain the full fly and use plain brand text.
Narrow screens use a small fly mark, with a minimal variant for very small widths.
Brand assets contain no layout logic. Welcome rendering reads no terminal state;
its caller supplies width and display capabilities. Local workspace, execution
label, optional server and execution directory appear in every layout and in
plain output. Locations wrap without ellipsis. Short screens use native terminal
scrollback in the built-in frontend.
