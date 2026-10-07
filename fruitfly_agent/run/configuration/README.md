# Harness Configuration

[Up: Run](../README.md)

Store runtime selections independently of model specifications and mechanism definitions. This module reads and writes YAML; it does not construct Providers or run algorithms.

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

| Reference | Purpose |
|---|---|
| [Configuration reference](../../../CONFIGURATION.md) | File locations, environment variables, and selection behavior |
| [Catalog](../../lab/catalog/README.md) | Mechanism declarations and validation |
| [Run](../README.md) | Artifact resolution and actual runtime identity |

```bash
.venv/bin/python -m unittest tests.run.test_profiles.HarnessProfileTest tests.run.test_configuration.HarnessSelectionTest -v
```
