# Task Materials

[Up: Improvement](../README.md)

[__init__.py](__init__.py) implements `WorkspaceTaskSource`. Explicit selected
workspace-relative files become immutable byte resources. Instructions, source and
environment identity remain separate from private answers and verification checks.

Traversal, symlinks and protected credential files are rejected.
`WorkspaceTaskSource.freeze()` reads each selected file completely and imposes no
per-file or aggregate byte limit itself. A host needing bounded material loading
must enforce admission before calling it and supply an appropriate artifact store.
Later evidence-workspace limits are separate and do not bound this initial read. Files are copied rather than linked to a live workspace. Binary originals
retain their bytes and media types. Reading a resource does not execute it or
provide an image/document renderer automatically. No recursive ambient file scan,
network download or Provider request occurs here.

Task execution uses a fresh input copy for each candidate. External task sources
implement the same material contract through an injected runner/source adapter.

Offline checks: `tests.lab.test_detached_editor`.
