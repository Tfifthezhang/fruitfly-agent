# Augmentation

[Up: Context Manager](../README.md)

Add bounded instructions or information to each model request without changing the canonical conversation.

| Module | Adds |
|---|---|
| [Skills](skills/README.md) | Names, descriptions, and file locations; the model reads full instructions when needed. |
| [Information spaces](information/README.md) | Retrieved file memory, local documents, or live HTTP results |

## Implement a transformer

| Concern | Contract |
|---|---|
| Method | `transform(frame)`, synchronous or asynchronous |
| Result | New `ContextFrame`, `ContextTransform(frame, metadata)`, or `None` |
| Input | Read-only, including nested messages; use `dataclasses.replace`. |
| Output | Relevant, bounded, and stable across repeated requests |
| I/O | Inject dependencies; keep synchronous transformations quick. |
| Errors | Core isolates ordinary failures; cancellation propagates. |
| Retrieved text | Treat it as untrusted data. |

See the [offline example](../../../../examples/extensions/README.md) and [Information protocols](information/README.md#extend-a-source). Verify output, unchanged input, empty results, repeated requests, and applicable failure/budget/cancellation paths.

```bash
.venv/bin/python -m unittest tests.lab.test_skill_catalog tests.lab.test_information_pipeline -v
```
