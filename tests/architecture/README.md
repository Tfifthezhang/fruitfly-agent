# Architecture Tests

[Up: Tests](../README.md)

Protect dependency direction, Core SDK independence, generic algorithm hosts, production/test separation, documentation navigation, and test discovery.

| Files | Protects |
|---|---|
| `checks.py` | Static import analysis, including relative/function/TYPE_CHECKING imports and supported literal dynamic imports |
| `test_boundaries.py / test_guard_detection.py` | Production rules and deliberate violation detection |
| `test_documentation.py` | READMEs, file/heading links, root reachability, parent/backlink tree, English text, project identity, and version consistency |
| `test_ci.py` | Execute the workflow's built-in prompt assertion offline to detect stale packaging checks; installed-wheel checks remain in CI. |
| `test_suite_structure.py / test_runner.py` | Discovery, shared helpers, explicit online isolation, and fail-fast guard execution |

Do not widen dependency allowances to make checks pass. Static checks do not analyze arbitrary reflection or execution.

```bash
.venv/bin/python -m unittest discover -s tests/architecture -t . -v
```
