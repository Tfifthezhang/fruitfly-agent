# Use OpenCode Go

[Up: Connections](../../README.md)

Connect your subscription key from the OpenCode console, select a cached model
and save/apply the configuration. Setup hides the key and stores it through the
selected credential backend. It does not turn a subscription key into API billing.

`__init__.py` registers the Go definition. `catalog.py` normalizes the authenticated
Go inference directory and leaves absent capability/limit metadata unknown.
`requests.py` supplies `User-Agent: fruitfly-agent/0.1` and a stable
`x-opencode-session` for the conversation, including auxiliary requests. Run binds
the Session identity; independent runtime construction gets an isolated fallback.
Every model currently uses Go's Chat Completions-compatible route. No native
Gemini protocol or model-name dispatch is added.

Cost and `opencode.allowance` are separate service receipts. Only declared finite,
nonnegative monetary fields and known billing-source labels are retained. Token
occupancy continues to use Chat's native prompt count; billed cache tokens do not
replace context occupancy. Extra Usage can be enabled in the service console;
FruitFlyAgent does not change it or automatically choose another billing path.

References: [Go access and client requirements](https://opencode.ai/docs/console/go/),
[model directory](https://opencode.ai/docs/console/api/models),
[inference receipts](https://opencode.ai/docs/console/api/inference).
Use coding-agent traffic permitted by the plan. Offline validation does not prove
account entitlement, region support or current model availability.

Checks: `tests.providers.test_connections`, `tests.providers.test_subscription_requests`,
`tests.run.test_model_connections`.

## Use a workspace secret variable

For a shell-only host, put the subscription key in your private
`.fruitfly/secrets.env` as `OPENCODE_GO_KEY`. Use the variable name in
`subscriptions.yaml` wherever the named connection would otherwise reference
an account:

```yaml
connections:
  go-personal:
    integration: opencode-go
    credential:
      env: OPENCODE_GO_KEY
```

Keep the credential file owner-readable only and outside exports and task
containers. The CLI's process environment takes precedence over the file.
The connection keeps the Go endpoint, request policy, and billing receipts.
Restart or apply a freshly loaded configuration after changing this key.
In the account picker, select **Use a key variable from secrets.env…** and enter
the variable name. The wizard checks the key and opens the model directory.
Saving records the variable name. The account flow continues to store pasted
keys in the selected credential store.

When the directory confirms reasoning effort choices, **Advanced settings**
offers the available values. **Service default** omits the override.


## Diagnose reasoning and regional failures

Chat reasoning extensions are decoded and retained through the shared
[Provider codec](../../../PROVIDER_GUIDE.md#preserve-chat-reasoning-extensions),
including tool follow-up. Unknown structures remain explicit protocol failures.
The workspace Privacy setting must allow Global for restricted DeepSeek models.
Changing that setting affects subsequent service requests; it does not repair a
local response decoder. Real model availability remains separately unverified.
