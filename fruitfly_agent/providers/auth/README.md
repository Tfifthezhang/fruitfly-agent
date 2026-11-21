# Manage account authentication

[Up: Providers](../README.md) · [Connections](../connections/README.md)

Authentication is independent of model message protocols. `AuthSession` supplies a
request-local bearer token and a stable authorization binding. Normal refresh does
not change the binding. Sign-out, a different registration or changed authorization
identity prevents later requests using the old runtime. Adapters implement the
optional `AuthenticatedAdapter` methods; Core does not know account authentication.

| File | Responsibility |
|---|---|
| `contracts.py` | Credential storage, authentication interaction and adapter ports |
| `stores.py` | System keyring or explicitly selected owner-only files, atomic updates and process locks |
| `environment.py` | Static subscription authorization from an explicit secret variable |
| `session.py` | Credential readiness, serialized rotation, bounded request-time renewal |
| `oauth.py` | PKCE, state, nonce, loopback listener and cancellable authorization attempts |

Account storage is user-scoped under `$XDG_CONFIG_HOME/fruitfly-agent` or
`~/.config/fruitfly-agent`. `storage.json` records the selected backend; `accounts/`
contains protected records and locks. With system storage, the account files contain
only display metadata and secret records stay in the keyring. A missing/unavailable
keyring never silently selects files. Choose Protected local files explicitly in
the connection flow. Account tokens never belong in project YAML or model snapshots.

`FileCredentialStore` requires a private directory and 0600 regular files and
rejects final symlinks. `modify()` serializes read/refresh/write across processes.
A rotating refresh is allowed to finish storing its replacement after a caller
cancels waiting; the cancelled request never proceeds to inference. Request-time
renewal is bounded and cannot open a browser. No token refresh occurs on startup,
configuration inspection or directory-cache reads.

An account authorization is separate from the project configuration transaction.
Discarding a model draft retains the connected account. Sign-out clears renewable
credentials, attempts provider-supported revocation and reports when remote
revocation was not confirmed. Existing API environment-key staging is unchanged.
Local guards do not sandbox arbitrary trusted code or unrestricted task containers.

Offline checks: `tests.providers.test_auth`, `tests.providers.test_connections`.

Static-key directory bindings use `bindings.py` and a private local record.
The record retains a random salt, a keyed fingerprint, and an opaque binding.
It contains no key value. Reusing the variable and key preserves the directory
scope across restarts. Replacing the key creates a different binding.

Environment-backed runtime authorization uses the same binding calculation.
The default records live in the user authentication directory under
`bindings/`. Embedding hosts can supply `ProviderRegistry.binding_directory`
to use their private state directory. Access-token values stay out of the
runtime identity.

## Authorize a headless host

Install FruitFlyAgent on the host and explicitly choose its credential backend:

```bash
python3 -m fruitfly_agent.providers.auth storage file
python3 -m fruitfly_agent.providers.auth login chatgpt
python3 -m fruitfly_agent.providers.auth status
```

Login contacts the authorization service. Open the displayed URL on a machine
with a browser. If the browser redirects to an unavailable loopback address,
copy the complete callback URL from its address bar into the hidden server
prompt. State, nonce, PKCE and callback validation remain mandatory. The attempt
expires after five minutes. No browser is launched on the server.

## Deploy one existing account through SSH

First select protected-file storage on the server with the command above.
Then run this on the machine holding the selected registration:

```bash
python3 -m fruitfly_agent.providers.auth status
python3 -m fruitfly_agent.providers.auth deploy ACCOUNT_ID user@server \
  --python /home/user/venv/bin/python
```

`ACCOUNT_ID`, `user@server` and the Python path are placeholders. SSH must already
have working host-key verification and noninteractive authentication; deployment
does not disable either check. This operation contacts the SSH server. Secrets
travel only on SSH stdin. The receiver stores only the selected registration,
using its configured backend and atomic record replacement. It preserves the
server's host identity, other registrations and workspace configuration. Existing
registrations require explicit `--replace`; an integration mismatch is rejected.
Failure diagnostics never repeat remote output or the transferred payload.

Refreshing a copied renewable registration independently on two hosts can
invalidate a rotating refresh token. Prefer a separate login on each host; after
transferring a registration, use one host to renew that registration. Deployment
does not copy directory caches, workspace keys or any entire credential folder.
OpenCode Go environment keys remain explicit variables in the private workspace
`secrets.env`; this command transfers account registrations only.

Credential directory, file and lock checks require the current Unix owner and
private permissions. File reads reject final symlinks and nonregular files.
These checks do not isolate processes sharing the same Unix account or protect
against a host administrator.
