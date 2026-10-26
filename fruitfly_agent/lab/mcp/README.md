# MCP Tool Client

[Up: Lab](../README.md) · [Configuration](../../../CONFIGURATION.md#connect-mcp-tools) · [Examples](../../../examples/mcp/README.md)

Connect explicitly selected tools from independently installed local MCP servers.
The disabled-by-default `mcp-tools` mechanism uses the optional `mcp` extra.
Ordinary startup and Catalog discovery import neither the MCP SDK nor jsonschema.
This module implements a client; FruitFlyAgent does not expose an MCP server.

## Connect a service

1. Install `fruitfly-agent[mcp]` in the Agent environment. Dependency installation uses the network.
2. Install the desired server separately and choose its executable and tool names.
3. Copy and edit [mcp.example.yaml](../../../examples/configuration/mcp.example.yaml) as `.fruitfly/mcp.yaml`.
4. Enable `mcp-tools` under Tools in configuration. Save, then start or apply the configuration.
5. Review the executable, arguments, local directory and injected environment names before authorizing startup.

Configuration alone starts no process. Run calls the registered asynchronous
preparation contract before synchronous assembly. Each server is owned before
startup; initialization and every `tools/list` page complete before its selected
catalog is frozen. Missing selections, duplicate names, invalid schemas or a
failed server prevent activation. Failed replacement leaves the incumbent active.
No model request is needed for preparation.

| Setting | Meaning / default |
|---|---|
| `servers.NAME` | Stable service ID: 1–48 letters, digits, underscores or hyphens; starts with a letter or digit |
| `enabled`, `transport` | Boolean, default true; only `stdio` |
| `command`, `args` | Executable and argument array; no implicit shell or package installation |
| `cwd` | Local directory, relative to the local workspace by default |
| `tools` | Required nonempty list of exact remote tool names; no wildcard selection |
| `env` | Explicit non-secret process values, included in runtime identity |
| `secret_env` | Child variable → host secret-variable name; values are resolved at preparation and excluded from identity |
| `startup_timeout`, `call_timeout`, `close_timeout` | Positive seconds: 30, 120, 10 |
| `max_parallel` | Positive integer; 1 simultaneous dispatched request per service |
| `max_result_bytes` | Positive decoded catalog/reply budget; 16 MiB |
| `inline_result_chars` | Positive model-facing text display bound; 12,000 characters |

The configuration file must resolve inside the local workspace. Process directories
may point to separately installed servers. The SDK also inherits its documented
safe ambient environment allowlist, including PATH and HOME; the full host secret
environment is not copied. Use absolute executables for reproducible selection.
Configured secrets reach only the corresponding child. Do not put credentials in
`command`, `args` or `env`: these fields are reviewable and recorded.

## Understand permissions and location

Startup approval authorizes a local process with current-user OS permissions.
It is independent of model tool-call approval. Embedders supply
`RunApplicationFactory(tool_service_startup_approval=...)`; absence denies startup.
The CLI asks on a TTY and denies redirected startup. `--approve-tools` and
`--unrestricted` do not bypass this startup decision.

External calls use the existing Interactive authorization service. Allow-once,
per-tool runtime-session approval, denial, cancellation and `/permissions clear`
work through that service. Grants bind the generated tool name and complete frozen
service identity. Local shell execution grants and MCP read-only hints confer no
external-tool permission. Rebuilding or recovering creates fresh grants.
Concise authorization metadata excludes argument values.

Stdio always runs on the **local Agent host**, including when file and Bash tools
use an SSH environment. `/lab` lists service name, transport, directory, selected
remote tools and observed state separately from the execution environment.
Status makes no remote probes. MCP is a protocol boundary, not an OS sandbox;
the server can use its own filesystem, network and installed dependencies.

## Preserve schemas and replies

Generated names contain a service namespace and stable hash and fit 64 characters.
Selected input schemas remain unchanged in model declarations and snapshots.
Object-root JSON Schema draft 7, 2019-09 and 2020-12 support local references,
unions and nulls through jsonschema, without primitive coercion. Non-local schema
references and unknown dialects fail preparation; no reference is fetched.
Core's optional `AgentTool.validate_arguments` runs before and after argument hooks.
Other tools retain their existing validation behavior.

Model services impose their own schema-size and keyword constraints. Preserving
and locally validating a schema does not prove that a particular model endpoint
accepts it. The client never silently removes constraints. Select fewer tools or
use a server-supported compact schema profile when required.

Every accepted complete reply is stored as a content-addressed text artifact.
Text and identical structured JSON are merged once for display. Error flags and
image blocks retain their meaning. A generated `retained_result` reader pages only
references issued by that service in the current runtime; offsets count Unicode
characters. The complete artifact retains provenance, unsupported content blocks
and original fields. Unsupported resources are not fetched automatically.
Results are labelled as untrusted target data, not installed instructions.

Artifacts can contain sensitive target data. Their size budget is checked after
SDK decoding, so it is not a transport-memory or disk-quota guarantee. Images are
bounded by the reply byte budget, not the text display limit. The reader's issued
reference set is transient; recovery does not restore access through that reader
to prior-runtime results. Existing artifact files remain available to their owner.

## Handle failure and recovery

Startup, queue waits and dispatched calls have separate deadlines. Queue waits
use `call_timeout` and are cancellable by caller or signal. Cancellation asks the SDK to
cancel and drains the local request; it cannot guarantee rollback of remote effects.
Timeout or broken transport produces an unknown-outcome error and prevents more
calls until explicit configuration application. No automatic restart or replay.
Catalog-change notifications invalidate new calls without changing active schemas.

Shutdown drains requests and closes the SDK context in the same task that opened
it. The SDK owns child termination. Cleanup timeout is surfaced, with the client
retaining its owner task. The client is not an OS process-tree sandbox.
Server stderr is suppressed rather than copied into model output or Session logs.

Manifest schema 8 records compact service identities plus verified artifacts with
the selected declarations, command, non-secret settings, limits, server/protocol
metadata and generated names. Recovery validates history and required declaration
artifacts, then prepares current configuration. It does not replay completed or
uncertain requests. Older manifests retain their original validation semantics.
Improvement trials are blocked for these runtimes because there is no isolated
frozen external-service backend.

## Extend and verify offline

| File / public entry | Responsibility |
|---|---|
| `config.py`: `load_config`, `ServerConfig` | Offline stdio configuration and limits |
| `client.py`: `McpClient.start/call/close/status` | SDK context ownership, pagination, requests and observed state |
| `schemas.py`: `compile_schema` | Exact local validation without coercion |
| `tools.py`: `make_tools`, `tool_name` | Frozen Core declarations and stable namespaces |
| `results.py`: `ResultStore` | Complete artifacts, content mapping and issued-reference paging |
| `authorization.py`: `ExternalToolPolicy` | Separate external-tool grant scope |
| `registration.py`: `definition` | Catalog registration, preparation, identity and installation |

The [Catalog preparation contract](../catalog/README.md#prepare-external-tools)
is transport-neutral. Additional transports belong in Lab implementations;
Run and Interactive consume generic preparation, authorization and status views.
HTTP, OAuth, resources/prompts discovery, sampling, elicitation and server-provided
instruction installation are not implemented. The SDK's default behavior handles
unsupported server requests; no host credentials or model callback is supplied.

```bash
.venv/bin/python -m unittest tests.core.test_tool_validation tests.lab.test_mcp_config tests.lab.test_mcp_client tests.lab.test_mcp_tools tests.lab.test_mcp_authorization tests.run.test_mcp_tools tests.interactive.test_tool_services
```

Tests use a local standard-library JSON-RPC peer and fake Providers. Protocol tests
skip when the optional extra is absent. No external MCP server or model is called.
