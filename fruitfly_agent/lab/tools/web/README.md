# Web Tools

[Up: Tools](../README.md)

Search public sources with `web_search`, then read important URLs with `web_fetch`.
Both are Core `AgentTool` implementations, selectable under Tools in `/config`,
disabled by default, and independent of execution workflows.

## Enable the tools

Service fields are selections generated from the registered `choices`: search
supports `brave`, `tavily`, and `deepseek`; fetch supports `direct` and `deepseek`.
Use arrows and Enter, or numbered choices in line-based menus. Extension registries
supply their own choices without terminal changes; unsupported YAML values fail
validation.

In **Configure → Tools**, expand **Search the web** or **Fetch web pages** and
choose **Set up…**. Select the service, optionally enter an API key variable name,
then enter the key with hidden input. Choose **Stage settings**, return to startup,
and save/start a new session. Enabling a tool with missing credentials also opens
setup. Configured tools can be toggled without re-entering their key.

The form resolves credentials from the service and variable selected in that same
form. Direct fetch skips key input. Blank key input reuses an existing credential;
review shows only entered/reused status, never the value. Field `/clear` removes
an existing variable override so the selected service default is used. API keys
bypass input history and terminal echo. Values remain staged until configuration
save, which writes the workspace `.fruitfly/secrets.env` with owner-only permissions
and updates the current process. Existing legacy secret-file selection follows
[Configuration](../../../../CONFIGURATION.md#files-and-precedence), as for model keys.
Cancel, EOF, interruption or discarded configuration does not save new keys.
Ordinary save failures restore written files and retain the draft for retry.
Existing comments and unrelated credentials are preserved. An existing variable
with a different value is not overwritten; reuse it or choose another variable.

For manual configuration, enable **Search the web** and **Fetch web pages**, then
start a new session.
Search supports Brave (default), Tavily and DeepSeek. Put `BRAVE_SEARCH_API_KEY`,
`TAVILY_API_KEY` or `DEEPSEEK_SEARCH_API_KEY` in the process environment or `.fruitfly/secrets.env`.
`api_key_env` selects another variable name. Never put key values in YAML.
Direct fetching (default) needs no credential. DeepSeek fetching needs a DeepSeek
key in `DEEPSEEK_FETCH_API_KEY`. Model, search and fetch credentials use separate
default variables. Each tool's `api_key_env` can explicitly select another variable,
including `DEEPSEEK_API_KEY` to reuse a model key. The API accepts ordinary
DeepSeek keys; a special search-only key type is not required. Missing required
credentials fail construction.
Construction makes no network or model requests.

Add these entries alongside the active profile's existing `mechanisms`:

```yaml
- id: web-search-tool
  enabled: true
  parameters:
    backend: brave
    api_key_env: BRAVE_SEARCH_API_KEY
- id: web-fetch-tool
  enabled: true
```

Queries go to the selected service and may incur API charges. Source URLs go to
destination servers. Hosts inject keys through `AssemblyContext.secret_resolver`;
values do not enter configuration, manifests or local shell environments. Eval
explicitly forwards enabled tools' credentials into benchmark task containers. See
[Configuration](../../../../CONFIGURATION.md#environment-variables).

### Select DeepSeek search and fetch

Choose `deepseek` in each tool's **Set up…** form and enter its key, or merge these entries into
the selected profile's mechanisms and start a new session:

```yaml
- id: web-search-tool
  enabled: true
  parameters:
    backend: deepseek
    api_key_env: DEEPSEEK_SEARCH_API_KEY
- id: web-fetch-tool
  enabled: true
  parameters:
    backend: deepseek
    api_key_env: DEEPSEEK_FETCH_API_KEY
```

Search sends `POST /v1/tools/search` to `https://api.deepseek.com` with
`need_content=false`; bounded snippets prefer `summary`, falling back to `snippet`.
The existing count limit remains 1–10. Domain filters use `site:` with OR;
freshness uses a UTC `after:YYYY-MM-DD` cutoff (1/7/30/365 days). The complete
query including filters must fit 128 Unicode characters; longer queries fail
before HTTP and are never silently shortened. Date filtering is day-granular.

Fetch sends `POST /v1/tools/fetch` with the source URL and paginates the returned
Markdown without HTML extraction. Both endpoints use Bearer authentication.
DeepSeek fetch reports no final redirect URL, so output `url` remains the normalized
requested source URL. `content_id` hashes the API response body. Page extraction
capabilities depend on DeepSeek and the source site. HTTP 402 reports
`quota_exceeded` without retry; malformed/empty responses are not cached.
Both APIs are billed per successful request with results, separately from model
tokens. Prices and account limits are in the
[DeepSeek search/fetch guide](https://api-docs.deepseek.com/zh-cn/guides/search/).
No live service check runs during construction. Put each key value in the secret
environment, never YAML. Separate variables allow separately issued keys; they do
not create separate DeepSeek accounts, balances or account-level rate limits.

## Call the tools

| Tool | Arguments | JSON output |
|---|---|---|
| `web_search` | Required `query` (1–500 characters, at most 60 words; DeepSeek: 128 including filters); `count=5` (1–10); up to 10 `domains`; `freshness=any/day/week/month/year` | Titles, URLs, snippets, source IDs, retrieval time and cache status |
| `web_fetch` | Required public HTTP(S) `url`; `offset=1`; `limit=100` (1–200) | Source URL (final URL for direct fetch), title, numbered text, body hash, retrieval time and continuation offset |

Each tool's model-facing description declares its own use cases independently:
search discovers information and sources; fetch reads a known URL and verifies
source details. Neither description requires the other tool to be enabled. Fetch
services retain their own capability limits in their descriptions. See
[tool descriptions](../README.md#describe-visible-operations) for the shared contract.

Domain filters include subdomains and are checked against returned URLs. Results
are deduplicated after fragment removal. Brave uses `site:` operators and rejects
combined queries above 600 characters/75 words. Tavily uses basic search without
generated answers or raw content. Freshness is a service filter, not proof of
publication date. Titles have at most 300 characters; snippets 1200. Fetch important
sources before making factual claims; cite the returned source URL.

Direct fetching supports HTML, `text/*`, JSON and XML. HTML extraction removes scripts,
styles and embedded non-text content, keeps links and basic table boundaries, and
preserves preformatted indentation. Navigation may remain. There is no browser,
JavaScript rendering, login, cookie reuse, PDF parser or CAPTCHA bypass.

Output pages contain at most 20,000 text characters. Source lines over 1000
characters become multiple extracted lines, so continuation reaches every retained
character. Follow `next_offset` until null. `truncated` indicates more retained
lines; `source_truncated` separately reports the HTML extraction's 2,000,000-character
ceiling. Compare `content_id` (body SHA-256) across pages: expiration or eviction
can change contents. `source_id` identifies a normalized URL, not immutable text.
External content is untrusted data; tool notices cannot guarantee model behavior.

## Bound requests and state

Both mechanisms accept these YAML settings; model tool arguments cannot override them:

| Parameter | Default | Contract |
|---|---|---|
| `timeout_seconds` | 20 | Total queue, DNS, attempts, backoff, redirect and streaming deadline; maximum 120 |
| `max_retries` | 1 | Additional transient-error attempts; 0–2 |
| `max_response_bytes` | 2,000,000 | Decoded response limit; maximum 10,000,000 |
| `cache_ttl_seconds` | 300 | Successful-response lifetime; 0 disables; maximum 3600 |
| `cache_entries` | 32 | Runtime-local LRU responses; 0 disables; maximum 128 |
| `max_redirects` | 5 | Fetch redirects; maximum 10; search redirects disabled |

Transport failures and HTTP 408/429/500/502/503/504 retry with short exponential
backoff inside the original deadline. Authentication, forbidden, not-found and
quota errors do not retry. Each attempt can incur charges. This does not impose
a monetary or task-wide budget; later tool calls can repeat failed operations.

Each client serializes requests to coalesce identical concurrent cache misses.
Cache hits keep the original retrieval time. Header digests scope authentication.
Caches are runtime-local, not persisted, and hold at most
`cache_entries * max_response_bytes` body bytes per tool. Failed HTTP and rejected
adapter responses are not retained. Runtime close clears caches and closes HTTP.
Task cancellation and cancellation signals interrupt HTTP and queueing without
retry. Recovery creates fresh clients without replaying requests.

`WebError` contains safe JSON fields `code`, `message`, `retryable` and `status`.
Core marks the tool message as an error and prefixes the exception name. Codes
distinguish arguments/URLs, blocked destinations, timeout/network/auth/rate/quota
failures, malformed responses, unsupported/empty/oversized content and invalid
offsets. Raw service error bodies and credential headers are not returned.

## Apply host boundaries

The host recognizes `network_read`. Host-owned `PermissionPolicy.allow_network`
defaults to true and can deny these tools before execution. It does not restrict
Providers, live context, approved shell commands or trusted plugins. See
[Environment permissions](../../environment/README.md#apply-lightweight-permissions).

URLs require HTTP(S), standard ports and no embedded credentials. Private literal
addresses and local hostnames are rejected. For direct fetch and API destinations, DNS results and each redirect are
checked for public addresses; HTTPS downgrades are rejected. DNS preflight and
connection resolution are separate, so this is not DNS pinning or a complete SSRF
sandbox. Stronger guarantees need network isolation. HTTP verifies TLS and does not
inherit proxy/certificate environment settings. Direct fetching never uses search keys.
DeepSeek receives source URLs and fetches them remotely; local source URL syntax
and literal-address checks still apply, but source DNS and redirect checks belong
to DeepSeek. The client checks the DeepSeek API destination, not the source's DNS.
Enabled web tools register an original-task experiment blocker because live
responses have no frozen snapshots. Ordinary interactive use remains available.

## Extend and verify offline

Tools consume the small `SearchService` and `FetchService` protocols. They do not
interpret vendor HTTP responses. Adapters translate requests and responses; HTTP
owns bounded transport; Catalog owns configuration and resource assembly.

| File / public entry | Responsibility |
|---|---|
| [contracts.py](contracts.py) | `SearchRequest`, `SearchHit`, `SearchResponse`, `FetchResponse`, `SearchService`, `FetchService` |
| [client.py](client.py) | `WebClient`, `WebConfig`, `WebError`; HTTP, cache, destinations, cancellation and close |
| [registry.py](registry.py) | `WebServiceDefinition`, `WebServiceRegistry`, `default_service_registry`, `web_api_key_variable`; factories and credential defaults |
| [search.py](search.py): `create_web_search_tool` | Common argument checks, source filtering, deduplication and bounded tool output |
| [fetch.py](fetch.py): `create_web_fetch_tool` | Common argument checks, text pagination and numbered tool output |
| [common.py](common.py) | Shared output, source identity and text formatting helpers |
| [services/brave.py](services/brave.py) | Brave search parameters, authentication and response fields |
| [services/tavily.py](services/tavily.py) | Tavily basic search parameters, authentication and response fields |
| [services/deepseek.py](services/deepseek.py) | DeepSeek search and Markdown fetch, query limits and response parsing |
| [services/direct.py](services/direct.py) | Direct HTTP fetch and HTML/text extraction |
| [services/common.py](services/common.py) | Shared adapter JSON validation, secret redaction and invalid-response eviction |
| [registration.py](registration.py): `definitions` | Catalog declarations, service injection and owned clients |
| [__init__.py](__init__.py) | Public clients, contracts, registry and tool factories |

The small `services` package is covered here. Search responses carry typed hits,
retrieval time and cache state. Fetch responses carry text, source URL, optional
final URL, body identity, retrieval time, cache state and source truncation.
A missing final URL stays `None` inside the contract; the tool preserves the
existing output URL by falling back to the source URL. Services expose query
limits/descriptions and fetch descriptions without tool-side vendor branches.

To add a service, implement the relevant protocol and add a `WebServiceDefinition`
to the registry. Its factory receives a borrowed client and injected key. Register
search and fetch independently. Configuration choices come from the same registry;
there is no package scanning. `definitions(registry)` accepts an explicit registry
for hosts constructing their own Lab Catalog. Factories must remain offline and
adapters borrow their HTTP client rather than creating unmanaged transports.

`create_web_search_tool(service=service)` and `create_web_fetch_tool(service=service)`
accept a service directly. The existing client/backend/api_key calls remain
supported as construction conveniences. Both paths borrow their dependencies;
callers close owned HTTP clients. Search accepts at most 500 characters/60 words
and 10 results at the tool boundary; individual services enforce stricter combined
query limits before HTTP. Existing JSON arguments and output fields are retained.

Service definitions declare default credential variable names. Tool mechanisms
project these through `MechanismDefinition.credential_variables`;
[Catalog](../../catalog/README.md#declare-credential-requirements) resolves only
enabled requirements without constructing clients. Assembly checks missing keys
before calling the installer and injects a credential snapshot. Configuration
shows variable names with set/missing status and uses generic hidden setup forms. Eval consumes the same Catalog API
without recognizing individual tools or services. Direct fetch declares no keys.

Tests inject `httpx.MockTransport` and an async `check_url` callback to avoid DNS
and HTTP. Contract injection tests use a fake service without transport. Application
handles failed construction/startup cleanup and shutdown. Caches are runtime-local;
recovery constructs fresh clients. No ambient keys are read by this module.

```bash
.venv/bin/python -m unittest tests.lab.test_web_tools tests.lab.test_web_services tests.run.test_web_tools -v
```

Offline tests cover behavior and integration, not live API compatibility, search
quality or model quality. Protocol references:
[Brave Web Search](https://api-dashboard.search.brave.com/api-reference/web/search/get),
[Tavily Search](https://docs.tavily.com/documentation/api-reference/endpoint/search).
