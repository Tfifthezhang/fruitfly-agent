# Run Tests

[Up: Tests](../README.md)

Verify configuration, model selection, assembly, manifest, CLI, candidates, retention, and recovery.

| Files | Protects |
|---|---|
| `test_configuration.py / test_profiles.py` | Selection drafts, YAML, and persistence |
| `test_model_setup.py` | First-run form, secret isolation, preservation, cancel/discard, rollback, and immediate offline assembly |
| `test_assembly.py / test_resources.py` | Runtime identity and failed assembly cleanup |
| `test_cli.py` | Startup, one-shot, resume, and rebuild |
| `test_optimization_versions.py / test_task_prompt_catalog.py / test_base_prompt_flow.py` | Candidate scope, prompt selection, and recovery |
| `test_eval_bridge.py` | Optional Eval subprocess protocol; no benchmark scoring |

Fake Providers and temporary files. No model fees or benchmark containers.

Configuration and assembly tests share local setup helpers while keeping model inputs, manifest expectations, and rejection assertions in each scenario. Each test owns a temporary workspace; repeated assembly scenarios reset Provider call counts.

```bash
.venv/bin/python -m unittest discover -s tests/run -t . -v
```

Assembly checks bind permission identity to recovery, require the standard authorizer, protect the active Session writer, and construct fresh approval services.
