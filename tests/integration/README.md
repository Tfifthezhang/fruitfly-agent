# Integration Smoke

[Up: Tests](../README.md)

Explicit real Provider checks. These use the network, may incur charges, and are excluded from default offline discovery.

Copy and customize the [model template](../../examples/configuration/models.example.yaml), configure `.fruitfly/models.yaml` and `.fruitfly/secrets.env`, then choose an available profile. The command below uses the `deepseek-flash-openai` profile and requires a usable `DEEPSEEK_API_KEY`:

```bash
.venv/bin/python -m tests.integration.provider_smoke --models-file .fruitfly/models.yaml --model-profile deepseek-flash-openai --json .fruitfly/smoke/deepseek-flash-openai.json
```

| Input | Meaning |
|---|---|
| Model profile | Must exist and be usable by your account. |
| API key | Read from the environment variable named by `api_key_env`. |
| Output | Local smoke result; keep private runtime data out of source releases. |

Smoke outcomes report `sdk` and `protocol` separately, using the selected model
specification. Reading help or parsing a catalog does not run these paid scenarios.

See [Configuration](../../CONFIGURATION.md) and [Providers](../../fruitfly_agent/providers/README.md). Do not run this as an automatic documentation check.
# Local model relay transport

Run `.venv/bin/python -m unittest tests.integration.model_relay_socket` to
exercise the private Unix socket with a fake upstream. This check requires
permission to bind a local socket. It uses no external model or credential.


## Docker model access

On a native Linux rootless Docker host, set `FRUITFLY_ACCESS_TEST_IMAGE` to an
existing local Linux image with Python 3.12+ and FruitFlyAgent runtime
dependencies. Run `.venv/bin/python -m unittest tests.integration.eval_model_access`.
The check requires host OpenSSL. It mounts the checkout read-only and checks
default and explicit Agent identities through a fixture Unix socket and a
container-local TLS listener. The containers have no external network access.

## WorkBuddy SDK contracts

In an isolated controller with FruitFlyAgent's benchmarks extra (Harbor 0.23.0)
and WorkBuddy's declared runtime dependencies installed, set
`FRUITFLY_WORKBUDDY_CHECKOUT` to a reviewed source checkout. Make that checkout's
`src` importable in the controller without replacing Harbor from its upstream uv
lock. Run `LITELLM_LOCAL_MODEL_COST_MAP=True python -m unittest tests.integration.workbuddy_contract`.
This explicitly selected check uses the actual SDK, official verifier/environment
imports, complete generated JobConfig, named-source metric initialization and
read-only relay admission. It starts no Docker environment, downloads or model
requests. Installing its prerequisites can require network access. Container
permissions, host routing and real scoring remain separate integration checks.
