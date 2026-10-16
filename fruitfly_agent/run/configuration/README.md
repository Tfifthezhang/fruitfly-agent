# Harness Configuration

[Up: Run](../README.md)

Store runtime selections independently of model specifications and mechanism definitions. Manage configuration drafts and resolve model choices without constructing Providers or running algorithms. Candidate-backed menus are supplied through presentation callbacks.

```yaml
schema_version: 1
default_profile: default
profiles:
  default:
    model:
      catalog: models.yaml
      profile: deepseek-flash-openai
    mechanisms:
      - id: compaction
        enabled: true
        parameters: {}
```

| Field / API | Meaning |
|---|---|
| `HarnessConfig` | Schema version, default profile, and profile mapping |
| `HarnessProfile` | Model catalog/profile, prompt, artifact bindings, and mechanism selections |
| `prompt` | Optional; `assistant-default` or a text artifact ID |
| `artifact_bindings` | Named slots declared by enabled consumers |
| `load_harness_config(path)` | Parse and validate configuration. |
| `save_harness_config(path, config)` | Atomically replace the file. |
| Default location | `.fruitfly/config.yaml` |

The example uses `.fruitfly/models.yaml`, resolved relative to `.fruitfly/config.yaml`. Explicit catalog paths keep precedence over workspace discovery. See the [file selection rules](../../../CONFIGURATION.md#files-and-precedence).

Unknown fields and unsupported schema versions raise `ValueError`. Catalog validates mechanism IDs and parameters. Store key variable names in model specifications and key values in the environment; do not store secrets or full prompt text in YAML.

## Files and ownership

| File | Responsibility |
|---|---|
| [profile.py](profile.py) | Schema 1 values, YAML validation and persistence |
| [controller.py](controller.py) | Draft selection, edits, save/reset, and public profile operations |
| [operations.py](operations.py) | Narrow binding/profile edit contracts for host consumers |
| [resolution.py](resolution.py) | Workspace/profile discovery and model catalog resolution |
| [views.py](views.py) | Mechanism and prompt menu projections |
| [model_setup.py](model_setup.py) | Stage models and credentials through profile callbacks |
| [persistence.py](persistence.py) | Atomic byte writes for configuration operations |
| [migration.py](migration.py) | Explicit offline configuration relocation |

`profile()`, `stage_profile()`, and `changed` expose draft operations without allowing other services to access private fields. Model setup receives these callbacks and a configuration path. It writes only on save, preserves unrelated content, rolls back ordinary failures, and updates the secret environment after success. No model requests occur during configuration.

The public `RunConfigurationController` in [Run](../README.md) composes this controller with candidate-backed prompt presentation. The configuration implementation receives an artifact store and optional prompt-choice callback; it does not discover candidate paths or depend on runtime preparation. Default workspace paths and environment precedence are documented in the configuration reference below. Improvement methods have no configuration-menu category; `/improvement` owns method selection and per-job parameter overrides. Existing YAML entries remain optional defaults. Method-owned artifact slots registered independently of enablement remain valid adoption targets.

| Reference | Purpose |
|---|---|
| [Configuration reference](../../../CONFIGURATION.md) | File locations, environment variables, and selection behavior |
| [Catalog](../../lab/catalog/README.md) | Mechanism declarations and validation |
| [Run](../README.md) | Artifact resolution and actual runtime identity |

```bash
.venv/bin/python -m unittest tests.run.test_profiles.HarnessProfileTest tests.run.test_configuration.HarnessSelectionTest -v
```
