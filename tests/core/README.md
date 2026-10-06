# Core Tests

[Up: Tests](../README.md)

Verify messages, loop, hooks, tool dispatch, Session, failure isolation, and cancellation through Core public APIs.

| Files | Protects |
|---|---|
| `test_*.py` | Core behavior by topic |
| `../support/faux_provider.py / ../support/loop.py` | Scripted responses and loop fixtures |

Temporary Session files and fake Providers; no Provider SDK or real network.

```bash
.venv/bin/python -m unittest discover -s tests/core -t . -v
```
