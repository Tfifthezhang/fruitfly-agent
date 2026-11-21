# Connect subscription models

[Up: Providers](../README.md) · [Authentication](../auth/README.md)

Connections combine authentication, model discovery and protocol request policy.
`ConnectionRegistry` owns installed definitions; it is not a Lab algorithm or an
Improvement parameter registry. Run and Interactive consume the same definitions.
API access remains available through the existing model specification.

## Choose a connection

| Integration | Authentication | Model requests |
|---|---|---|
| [OpenCode Go](methods/opencode_go/README.md) | Subscription key from its console | Chat Completions through Go |
| [ChatGPT](methods/chatgpt/README.md) | Official Sign in with ChatGPT | Public Responses with plan consent |

In `/config`, open model → Add model and choose Subscription before selecting the service.
Subscription setup connects/reuses an account, then opens a searchable, paged
model picker. Only selected models enter project configuration. Favorites and
recent selections are separate local preferences. Connections manages account
labels, reauthorization, project references and explicit sign-out. Advanced model
settings stages validated request options without changing the active runtime.

API setup retains explicit protocol, model, capability and limit forms. There is
no new Gemini adapter. Claude subscription credential reuse is not admitted:
[Anthropic's authentication rules](https://code.claude.com/docs/en/legal-and-compliance#authentication-and-credential-use)
restrict third-party credential handling. [WorkBuddy's platform](https://open.workbuddy.cn/docs/third-party-app)
exposes application/agent tasks and requires approved application credentials;
that does not establish a model Provider contract. Full external Agent integrations
belong in Lab and may later reuse authentication ports. No inactive vendor stubs
or unofficial subscription proxies are installed.

## Keep startup offline

`CatalogCache.read()` never makes a network request. Startup uses saved model
configuration, not a newly downloaded catalog. The picker reads cached metadata
immediately. TTY lists update as background metadata arrives and preserve focus;
numbered fallback reloads on its next selection. On entering a stale or empty directory it starts one background
refresh; the default age is 24 hours. Old caches remain readable. Explicit Refresh
models requests an update. Failed refreshes retain the last complete snapshot,
back off and do not launch browser authentication. ETag/Last-Modified enable
conditional refresh when the service supports it. Concurrent requests in one
service instance merge. Caches are separated by integration, endpoint, account
registration/credential binding and region, with hashed filenames and normalized non-secret records.

A directory is a historical observation, not proof of current entitlement,
quota or availability. Missing limits require explicit documented values. Missing
tool/streaming support prevents harness selection. Incomplete or invalid catalogs
do not replace complete records. Refresh never switches models or rewrites saved
windows, capabilities or parameters. A newly absent model is not automatically
replaced. Review updated metadata and save/apply before changing execution.

## Store references and freeze execution

The wizard writes selected models to `subscriptions.yaml` and records the path
in `models.subscriptions` in the profile. The loader reads only referenced
catalogs and rejects duplicate aliases. The model-catalog grammar accepts optional root `connections`, `models`
and optional `metadata`. API entries retain explicit `sdk`/`protocol`/key variables.
Connected entries reference a root connection and freeze the chosen model values:

```yaml
connections:
  coding:
    integration: opencode-go
    account: replace-with-local-account-id
models:
  daily:
    connection: coding
    model: replace-with-catalog-model-id
    context_window: 131072
    max_output_tokens: 16384
    capabilities:
      tools: true
      streaming: true
      vision: false
      reasoning: false
```

Omitted optional parameters use service defaults. For subscription entries, an
omitted parallel tool call setting leaves that request field unset. An existing
explicit boolean is retained on updates.

Account/model IDs and numeric limits above are placeholders; use the picker or
verified service metadata. No key or token is stored here. Existing inline API
entries remain valid in the same parser. Unknown fields, conflicting connection
routes and API-key variables on connected entries fail. `models.roles` still
selects aliases and contains no subscription settings.

Resolved/frozen entries carry the complete SDK, protocol, endpoint, model values,
non-secret `access: {integration, account}` and `output_reserve`. This inline access
binding is also accepted by the current grammar for materialized execution; it
cannot override the registered route. Source account credentials and directory
caches are not frozen. A destination must authorize its referenced account.
Runtime identity records the stable account binding, protocol and effective
budgets; refresh tokens, access tokens and cache timestamps are excluded.

Ordinary changes use the existing guarded configuration save/apply transaction.
Concurrent catalog edits are rejected; failed writes retain the draft and restore
owned files. Account renewal and remote authorization are independent operations
and are not rolled back to obsolete credentials.

## Preserve harness behavior

Token usage, context occupancy and plan allowance are different observations.
Input/cache/reasoning counts retain the native protocol semantics. Missing receipts
stay unknown. Go's declared billing/allowance fields are retained separately in
model usage receipts; no remaining allowance is inferred from token counts.
`/status` shows the connection, account and conservative output reservation.

Connected routes do not inherit API input-count endpoints. Unsupported exact
counting falls back to marked estimates; strict measurement fails closed. ChatGPT
cannot enforce the output token field, so its confirmed model output maximum
remains reserved even when an auxiliary role asks for a smaller answer. Reduction,
images, tools and final admission use the existing shared measurement pipeline.
Directory changes cannot silently lower that reservation. Billing/quota failures
are distinct from context overflow and never trigger compaction or paid fallback.
Go's console may independently enable Extra Usage; manage that setting there.

Independent child/candidate runtimes retain separate context/measurement state and
borrow account authentication. Normal token rotation preserves exact continuation;
account/route changes cannot reuse it. Connection/account/endpoint and accounting
policy are protected infrastructure, outside Improvement field grants. Existing
H/S/I algorithms and their candidate-execution path are unchanged.

Harbor task containers use host-managed model relay grants for subscription
connections. Account credentials stay on the host. Local execution and research
continue to use the ordinary resolver without an Eval dependency. See the
[Harbor guide](../../../fruitfly_eval/harbor/README.md#connect-subscription-models).

## Extend a connection

| File | Owns |
|---|---|
| `contracts.py`, `registry.py` | Strict connection profiles, definitions and public `register_connection` |
| `catalog.py` | Atomic historical directory snapshots and cache scope |
| `service.py` | Explicit account operations, conditional refresh, deduplication and backoff |
| `runtime.py` | Request-time authentication through public adapter methods |
| `errors.py` | Bounded subscription error categories without raw remote text |
| `methods/<name>/` | Concrete authentication, discovery and request policies |

Register installed Python through `register_connection()` before loading catalogs.
Reuse the owning service table for endpoint metadata. Implement the auth method,
normalized complete directory and request/usage policy, plus optional refresh,
authorization and revocation callbacks. Protocol adapters implement public
`configure_connection`, `set_access_token` and `bind_session`; no factory or terminal
vendor dispatch is needed. YAML never imports implementation code. Declare frozen
resources and verify imports without checkout fallback for resource additions.

Offline checks: `tests.providers.test_auth`, `tests.providers.test_connections`,
`tests.providers.test_subscription_requests`, `tests.providers.test_catalog_cache`,
`tests.run.test_model_connections`.
Real browser authorization, directory refresh and inference use the network.
Inference consumes plan allowance and may incur charges under service settings;
none is performed by default tests.
