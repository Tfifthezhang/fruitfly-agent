# Run Tests

[Up: Tests](../README.md)

`test_host_services.py` exercises search receipts, candidate activation checks, evolution operations, and model-setup rollback using explicit fake capabilities without a Factory. Architecture checks protect the corresponding service boundaries.

Verify configuration, model selection, assembly, manifest, CLI, candidates, retention, and recovery.

| Files | Protects |
|---|---|
| `test_component_configuration.py` | Schema-2 parsing/assembly, exact text, derived configuration, portable candidate reload, registered resource capture and source integrity |
| `test_runtime_spec.py` | Shared profile types, Core defaults, explicit reference conflicts and strict scalar candidates |
| `test_configuration_application.py` | Same-Session model changes, original history, empty-session application, failed startup recovery and exclusive writer lease lifetime |
| `test_configuration.py / test_profiles.py` | Selection drafts, YAML, and persistence |
| `test_execution_policy.py` | Guarded/unrestricted native file and shell behavior, environment inheritance, cancellation and launch validation |
| `test_execution_limits.py` | Configured task tool limits, runtime identity and detached-trial facts |
| `test_defaults.py` | Default restoration drafts, model/key preservation, save/discard and read-only default files |
| `test_model_setup.py` | First-run form, editable medium parameter defaults, JSON retries before credentials, server-default opt-out, secret isolation, rollback and immediate offline assembly |
| `test_model_catalog.py` | Uniform menu field order, transport last, comment/literal preservation, flow entries and semantic equality across old/new model entries |
| `test_mechanism_setup.py` | Guided SSH enable/repair, hidden account/password, per-field retries, shared model/SSH persistence and rollback |
| `test_web_setup.py` | Hidden web keys, pending service/variable bindings, direct fetch, cancel/discard, rollback and same-process startup |
| `test_assembly.py / test_resources.py` | Runtime identity, complete visible runtime descriptions, registration-owned display categories and failed assembly cleanup |
| `test_web_tools.py` | Search credential injection, network-read policy, offline Application search/fetch, recovery and HTTP resource cleanup |
| `test_mcp_tools.py` | Optional stdio tool preparation, selected identity, separate approvals, current-config recovery, failed apply and multi-server cleanup |
| `test_ssh_environment.py` | Distinct local/remote descriptions, draft/save isolation, successful and failed activation, SSH selection, secret-free identity, remote file tools, current-target recovery and failed-resource cleanup |
| `test_cli.py` | Direct welcome without menu input/model calls, --configure, missing-key repair/cancellation, invalid-file preservation, save failure, one-shot, resume and rebuild |
| `test_improvement_versions.py / test_task_prompt_catalog.py / test_base_prompt_flow.py` | Candidate scope, prompt selection, and recovery |

Fake Providers and temporary files. No model fees or benchmark containers.

Configuration and assembly tests share local setup helpers while keeping model inputs, manifest expectations, and rejection assertions in each scenario. Each test owns a temporary workspace; repeated assembly scenarios reset Provider call counts.

```bash
.venv/bin/python -m unittest discover -s tests/run -t . -v
```

Assembly checks record permission identity while allowing configuration changes on resume, require the current authorizer, protect the Session writer, and construct fresh approval services.

`test_model_usage.py` verifies main/auxiliary observations, atomic
receipts and rejection before an additional Provider invocation.

Assembly details live in `test_assembly.py`; manifest/environment recovery rules
live in `test_recovery.py`, and content-addressed storage in `test_artifacts.py`.
CLI parsing is covered by `test_cli.py`; execution, configuration startup and
session discovery have separate `test_cli_execution.py`,
`test_cli_configuration.py` and `test_session_discovery.py` owners. Model wizard
interaction, persistence and declaration validation use `test_model_setup.py`,
`test_model_persistence.py` and `test_model_configuration.py`, sharing an explicit
workspace fixture rather than importing test classes.
