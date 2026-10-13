# Terminal Rendering

[Up: Terminal](../README.md)

Present frontend events, canonical history, Markdown, and status. Rendering observes public views and does not submit work or activate runtimes.

| File / entry | Responsibility |
|---|---|
| [renderer.py](renderer.py): TerminalRenderer | Event display, stream output, history, and display cleanup |
| [history.py](history.py) | Static canonical conversation rendering |
| [markdown.py](markdown.py) | Markdown formatting and streamed presentation |
| [welcome.py](welcome.py), [branding.py](branding.py) | Welcome/status layout and project identity |

Use [Contracts](../../contracts/README.md) for event/status/history inputs and [I/O](../io/README.md) for safe text, terminal capabilities, and inline display primitives. This layer never imports features or TerminalFrontend.

History display preserves full user/assistant text while omitting private reasoning, image bytes, and tool arguments. Tool output has explicit display bounds. TERM/NO_COLOR affect ANSI and color through the I/O layer. These presentation rules do not change canonical messages or model context. No model calls, tools, or persistence effects.

Live reasoning text, including Provider reasoning summaries, is hidden from the transcript. Existing activity events show reasoning status and elapsed time in the inline display; non-interactive output prints activity milestones without animation. Hidden reasoning deltas do not flush Markdown, add blank lines, or reset activity timing. Completion, failure, cancellation, and renderer cleanup clear the activity display. Hiding text does not reduce model reasoning usage or add model requests.

```bash
.venv/bin/python -m unittest tests.interactive.test_terminal_renderer tests.interactive.test_markdown tests.interactive.test_welcome tests.interactive.test_conversation -v
```
