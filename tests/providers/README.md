# Provider Tests

[Up: Tests](../README.md)

Verify model specifications, registry, codecs, errors, and public streams with SDK substitutes.

| Files | Protects |
|---|---|
| `test_deadlines.py` | Quiet headers/chunks, keepalive, thinking progress, total/backoff deadlines, partial failure, signal cancellation, retry hints, and bounded cleanup |
| `test_streams.py` | Text/thinking/tool deltas, enabled tool descriptions with an unchanged base prompt, final results, usage, request limits, retries, cancellation, and stream cleanup |
| `test_*.py` | Catalog configuration and message/error mapping |
| `test_configuration_contract.py` | Separate SDK/protocol fields, pair dispatch, unsupported-pair and old-field rejection, request/transport separation, service constraints and duplicate-key rejection |
| `test_continuation.py` | Exact response/phase/signature replay, Session restore, context changes, Chat tools, unknown usage and non-final responses |
| `test_service_presets.py` | Qwen/BigModel template and wizard agreement, native thinking options, unsupported controls, streaming tools and reasoning replay |

No real API calls. Use the explicit Integration entry for network smoke.

```bash
.venv/bin/python -m unittest discover -s tests/providers -t . -v
```
