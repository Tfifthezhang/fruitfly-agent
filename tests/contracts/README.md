# Contract Tests

[Up: Tests](../README.md)

Preserve reviewed public interfaces and independent persistence fixtures.

| Files | Protects |
|---|---|
| `api_baseline.py / test_public_api.py` | Public exports and responsibility boundaries |
| `test_signatures.py` | Important argument/default/type and sync/async contracts |
| `test_persistence.py` | Session, RuntimeManifest v5, Eval request v2, and unsupported-version rejection |
| `test_evaluation_request.py` | Request validation and rejection of unsupported experiment inputs |

Never regenerate a baseline from the implementation. Treat failures as drift until an explicitly authorized contract change is reviewed.

```bash
.venv/bin/python -m unittest discover -s tests/contracts -t . -v
```
