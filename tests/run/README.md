# Run Tests

[Up: Tests](../README.md)

`test_host_services.py` exercises search receipts, candidate activation checks, evolution operations, and model-setup rollback using explicit fake capabilities without a Factory. Architecture checks protect the corresponding service boundaries.

Verify configuration, model selection, assembly, manifest, CLI, candidates, retention, and recovery.

| Files | Protects |
|---|---|
| `test_runtime_spec.py` | Shared profile types, Core defaults, explicit reference conflicts and strict scalar candidates |
| `test_configuration_application.py` | Same-Session model changes, original history, empty-session application, failed startup recovery and exclusive writer lease lifetime |
| `test_configuration.py / test_profiles.py` | Selection drafts, YAML, and persistence |
| `test_execution_policy.py` | Guarded/unrestricted native file and shell behavior, environment inheritance, cancellation and launch validation |
| `test_execution_limits.py` | Configured task tool limits, runtime identity and detached-trial facts |
| `test_defaults.py` | Default restoration drafts, model/key preservation, save/discard and read-only default files |
| `test_model_setup.py` | First-run form, secret isolation, preservation, cancel/discard, rollback, and immediate offline assembly |
| `test_mechanism_setup.py` | Guided SSH enable/repair, hidden account/password, per-field retries, shared model/SSH persistence and rollback |
| `test_web_setup.py` | Hidden web keys, pending service/variable bindings, direct fetch, cancel/discard, rollback and same-process startup |
| `test_assembly.py / test_resources.py` | Runtime identity, complete visible runtime descriptions, registration-owned display categories and failed assembly cleanup |
| `test_web_tools.py` | Search credential injection, network-read policy, offline Application search/fetch, recovery and HTTP resource cleanup |
| `test_ssh_environment.py` | Local/remote environment labels in configuration and runtime views, SSH selection, secret-free identity, remote file tools, recovery and failed-resource cleanup |
| `test_cli.py` | Startup, one-shot, resume, and rebuild |
| `test_improvement_versions.py / test_task_prompt_catalog.py / test_base_prompt_flow.py` | Candidate scope, prompt selection, and recovery |

Fake Providers and temporary files. No model fees or benchmark containers.

Configuration and assembly tests share local setup helpers while keeping model inputs, manifest expectations, and rejection assertions in each scenario. Each test owns a temporary workspace; repeated assembly scenarios reset Provider call counts.

```bash
.venv/bin/python -m unittest discover -s tests/run -t . -v
```

Assembly checks record permission identity while allowing configuration changes on resume, require the current authorizer, protect the Session writer, and construct fresh approval services.

`test_model_budget.py` verifies a shared main/auxiliary request allowance, atomic
receipts and rejection before an additional Provider invocation.
