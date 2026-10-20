# Task Materials

[Up: Improvement](../README.md)

[__init__.py](__init__.py) implements `WorkspaceTaskSource`. Explicit selected
workspace-relative files become immutable byte resources. Instructions, source and
environment identity remain separate from private answers and verification checks.

Traversal, symlinks, protected credential files and oversized complete inputs are
rejected. Files are copied rather than linked to a live workspace. Binary originals
retain their bytes and media types. Reading a resource does not execute it or
provide an image/document renderer automatically. No recursive ambient file scan,
network download or Provider request occurs here.

Task execution uses a fresh input copy for each candidate. External task sources
implement the same material contract through an injected runner/source adapter.

Offline checks: `tests.lab.test_improvement_pipeline`.
