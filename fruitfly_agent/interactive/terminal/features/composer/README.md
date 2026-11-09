# Compose text and images

[Up: Terminal features](../README.md)

`Composer` owns selected frozen images and their ranges in an editable prompt.
`transform` resolves explicit `@"path"` references or a standalone dropped path;
`paste` handles quoted or shell-escaped multi-file drops; `paste_image` consumes an
injected clipboard capability. `prepare` produces the existing UserContent blocks
in prompt order. Literal marker text cannot reconstruct image selections.

| Operation | Behavior |
|---|---|
| Ctrl+V | Read a clipboard image and insert a numbered marker |
| Drop image paths | Validate files and insert markers at the cursor |
| Backspace/Delete | Remove an entire selected marker |
| Left/Right | Move across a marker as one item |
| Enter | Submit text/images; image-only prompts work |
| Failed preflight | Keep the draft for editing or retry |
| Successful submission, session switch, Ctrl+C | Clear pending input |

The [I/O editor](../../io/README.md#adapt-structured-input) consumes generic atomic
ranges and injected callbacks. It knows no image policy. Run supplies bounded
[clipboard access](../../../../run/runtime/clipboard.py); the host's existing image
reader resolves local paths and validates format, size and vision support.
Platform clipboard support is optional; plain/readline input accepts paths.

Selections are transient frontend state until ordinary Application submission.
No new model call, filesystem writer, Agent loop or runtime activation path exists.
The image loader freezes bytes at selection time. Audio/video and a local GUI
file picker are not implemented. See [terminal image input](../../README.md#attach-local-images)
for supported formats, limits and SSH behavior.

Offline checks: `tests.interactive.test_composer`, `tests.run.test_clipboard`,
`tests.workflows.test_multimodal`. PTY tests use injected clipboard images. Actual
platform clipboard and terminal drag/drop behavior require a local manual check.
