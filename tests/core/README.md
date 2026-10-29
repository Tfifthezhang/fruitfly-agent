# Core Tests

[Up: Tests](../README.md)

Verify messages, loop, hooks, tool dispatch, Session, failure isolation, and cancellation through Core public APIs.

| Files | Protects |
|---|---|
| [test_media.py](test_media.py) | Frozen inputs, media formats, container checks, declared MIME, image count and byte limits |
| `test_authorization.py` | Final arguments, fail-closed decisions, and cancellation before execution |
| `test_tool_observation.py` | Isolated result callbacks, success-hook compatibility, unknown tools and budget rejection |
| `test_execution_facts.py` | Termination causes, attempted/started/skipped tools, declared tool errors and unchanged result status |
| `test_*.py` | Core behavior by topic |
| `../support/faux_provider.py / ../support/loop.py` | Scripted responses and loop fixtures |

Temporary Session files and fake Providers; no Provider SDK or real network.

```bash
.venv/bin/python -m unittest discover -s tests/core -t . -v
```
