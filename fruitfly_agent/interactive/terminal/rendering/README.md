# Terminal Rendering

[Up: Terminal](../README.md)

Present frontend events, canonical history, Markdown, and status. Rendering observes public views and does not submit work or activate runtimes.

| File / entry | Responsibility |
|---|---|
| [renderer.py](renderer.py): TerminalRenderer | Event display, stream output, history, and display cleanup |
| [tools.py](tools.py) | Shared bounded argument/result summaries and sensitive argument-name redaction |
| [history.py](history.py) | Static canonical conversation rendering |
| [markdown.py](markdown.py) | Markdown formatting and streamed presentation |
| [welcome.py](welcome.py), [branding.py](branding.py) | Welcome/status layout and project identity |

Use [Contracts](../../contracts/README.md) for event/status/history inputs and [I/O](../io/README.md) for safe text, terminal capabilities, and inline display primitives. This layer never imports features or TerminalFrontend.

Submitted input is echoed once with an accented bold `❯` prefix, `│` continuation lines, and blank lines before and after it. Bodies keep their ordinary text weight. Resumed user messages have a bold **You** label. No full-row fill or width-dependent border is committed to scrollback; color-disabled output retains the prefixes and spacing. History display preserves full user/assistant text while omitting private reasoning, image bytes, and tool arguments. Tool output has explicit display bounds. TERM/NO_COLOR affect ANSI and color through the I/O layer. These presentation rules do not change canonical messages or model context. No model calls, tools, or persistence effects.

Live reasoning text, including Provider reasoning summaries, is hidden from the transcript. Existing activity events show reasoning status and elapsed time in the inline display; non-interactive output prints activity milestones without animation. Hidden reasoning deltas do not flush Markdown, add blank lines, or reset activity timing. Completion, failure, cancellation, and renderer cleanup clear the activity display. Hiding text does not reduce model reasoning usage or add model requests.

```bash
.venv/bin/python -m unittest tests.interactive.test_input_emphasis tests.interactive.test_terminal_renderer tests.interactive.test_markdown tests.interactive.test_welcome tests.interactive.test_conversation -v
```

Tool rows display the tool-owned action description with an explicit running,
completed, failed, cancelled or unknown-outcome marker. Arguments and elapsed time
use reduced emphasis. Tool names remain secondary metadata; rendering has no
branches for concrete tools. Unknown legacy outcomes display Finished rather than
Completed. Descriptions and tool text escape terminal control characters.

Default live tool output shares an 800-character display allowance per run because
the existing partial-output callback does not identify individual calls. Concurrent
starts do not reset that allowance. Final output has a bounded summary; failed and
cancelled results retain a bounded reason preview. `/tools` lists retained results;
`/tools CALL_ID` shows their full retained output and bounded argument metadata via
the [tool detail feature](../features/README.md). Truncated rows point to that command.
These are event-window views, not durable full-output archives. Tool-side truncation
still applies; late inspection may find that old events have been evicted.
