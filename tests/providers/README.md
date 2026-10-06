# Provider Tests

[Up: Tests](../README.md)

Verify model specifications, registry, codecs, errors, and public streams with SDK substitutes.

| Files | Protects |
|---|---|
| `test_streams.py` | Text/thinking/tool deltas, final results, usage, request limits, retries, cancellation, and stream cleanup |
| `test_*.py` | Catalog configuration and message/error mapping |

No real API calls. Use the explicit Integration entry for network smoke.

```bash
.venv/bin/python -m unittest discover -s tests/providers -t . -v
```
