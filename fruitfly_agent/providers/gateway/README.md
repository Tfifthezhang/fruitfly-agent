# Model relay

[Up: Providers](../README.md)

`ModelRelay` validates an opaque grant, a frozen upstream route, the model
identifier, and the request size before obtaining an upstream credential.
The caller owns the HTTP client and streaming response lifetime. Grant
expiration and revocation prevent subsequent requests. Revoking a grant cancels its active forwarding tasks. Listener shutdown waits
for owned connection cleanup.

The relay accepts model inference only. `RelaySocket` serves a private Unix
socket, bounds incoming requests, and closes active streams on disconnect or
listener shutdown. `RelayTransport` binds an HTTP client to a single upstream
route and sends its opaque grant through the socket. The socket path must be
inside an owner-only directory. The host owns container mounts and task grants.

Responses and Chat Completions adapters accept an explicit `http_client` at
construction. Hosts can supply a client using `RelayTransport` while retaining
the original model endpoint for protocol and continuation identity. The injected
client follows the adapter SDK's close lifecycle. This is a construction port,
not a YAML request parameter. Harbor supplies per-trial mounting and grant lifecycle through its
[host access owner](../../../fruitfly_eval/harbor/README.md#connect-subscription-models).

## Cross a Docker Desktop virtual machine

A macOS Unix socket bind mount is not a usable Linux socket in Docker Desktop.
An explicit network listener can be selected with `RelaySocket(listen=(host,
port), tls=server_context)`. Network mode requires TLS. `RelayTransport` accepts
`network_url` and a client TLS context requiring certificate and hostname
verification. The host supplies certificates and network reachability; insecure
HTTP and disabled identity checks are rejected. Grant, route, streaming and
connection limits are unchanged. Native Linux hosts can retain Unix sockets.
Harbor selects this mode through machine-local model relay settings.

`default_registry(http_client_factory=..., authorization_factory=...)` assembles
protocol adapters with explicit host-supplied access. The authorization factory
supplies stable account identity and request-time authorization. The HTTP client
factory supplies scoped routing. Both receive the resolved model specification.
This path avoids accessing a container-local account store. Clients follow the
adapter close lifecycle, so each constructed adapter needs its own client.


`access.py` loads an owner-only task descriptor and supplies the registry's HTTP
client and authorization factories. It checks frozen model identity and preserves
account binding across temporary grant changes. Descriptor grants are secrets;
they must not enter Sessions, reports, or ordinary configuration.
