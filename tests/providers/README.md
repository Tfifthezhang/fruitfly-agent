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
| [test_media.py](test_media.py) | Attributed Chat images after complete tool batches, native image encoding, nonvision projections and exact follow-up reasoning |
| `test_service_presets.py` | Explicit Qwen examples, unchanged authored parameters, streaming tools and reasoning replay |
| `test_service_protocols.py` | All 10 named service/protocol pairs, unchanged YAML round trips, table addresses/default SDKs, images, two-tool continuation and absence of model-specific policies |
| `test_service_table.py` | Packaged table discovery, data-only endpoint changes and strict metadata validation |

No real API calls. Use the explicit Integration entry for network smoke.

```bash
.venv/bin/python -m unittest discover -s tests/providers -t . -v
```

`test_continuation.EmptyResponseTests` owns empty terminal response rejection,
available usage retention, no automatic retry and safe historical fallback replay.

`test_auth.py`, `test_connections.py`, `test_subscription_requests.py` and
`test_catalog_cache.py` cover account storage/rotation, catalog caching, strict
connection references, request policies and token/allowance separation offline.

`test_auth_transfer.py` verifies selected-registration SSH transfer, explicit
replacement, private publication, bounded invalid payload rejection and secret-free
command arguments and errors. SSH and authorization-service calls are substituted.

Chat reasoning extension regressions in `test_subscription_requests.py` cover
alternate reasoning fields, dialect-specific detail replay and tool follow-up.
