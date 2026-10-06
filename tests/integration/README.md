# Integration Smoke

[Up: Tests](../README.md)

Explicit real Provider checks. These use the network, may incur charges, and are excluded from default offline discovery.

Copy and customize the [model template](../../models.example.yaml), configure `models.yaml` and `.env`, then choose an available profile. The command below assumes you have replaced all placeholders in `example-responses` with a working model configuration:

```bash
.venv/bin/python -m tests.integration.provider_smoke --models-file models.yaml --model-profile example-responses --json .fruitfly/smoke/example-responses.json
```

| Input | Meaning |
|---|---|
| Model profile | Must exist and be usable by your account. |
| API key | Read from the environment variable named by `api_key_env`. |
| Output | Local smoke result; keep private runtime data out of source releases. |

See [Configuration](../../CONFIGURATION.md) and [Providers](../../fruitfly_agent/providers/README.md). Do not run this as an automatic documentation check.
