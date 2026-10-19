# Web Tools

[Up: Tools](../README.md)

Search public sources with `web_search`, then read important URLs with `web_fetch`.
Both are Core `AgentTool` implementations, selectable under Tools in `/config`,
disabled by default, and independent of execution workflows.

## Enable the tools

Enable **Search the web** and **Fetch web pages**, then start a new session.
Search supports Brave (default) and Tavily. Put `BRAVE_SEARCH_API_KEY` or
`TAVILY_API_KEY` in the process environment or `.fruitfly/secrets.env`.
`api_key_env` selects another variable name. Never put key values in YAML.
Fetching needs no search credential. Missing credentials fail search construction.
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
values do not enter configuration, manifests or child environments. See
[Configuration](../../../../CONFIGURATION.md#environment-variables).

## Call the tools

| Tool | Arguments | JSON output |
|---|---|---|
| `web_search` | Required `query` (1–500 characters, at most 60 words); `count=5` (1–10); up to 10 `domains`; `freshness=any/day/week/month/year` | Titles, URLs, snippets, source IDs, retrieval time and cache status |
| `web_fetch` | Required public HTTP(S) `url`; `offset=1`; `limit=100` (1–200) | Final URL, title, numbered text, body hash, retrieval time and continuation offset |

Domain filters include subdomains and are checked against returned URLs. Results
are deduplicated after fragment removal. Brave uses `site:` operators and rejects
combined queries above 600 characters/75 words. Tavily uses basic search without
generated answers or raw content. Freshness is a service filter, not proof of
publication date. Titles have at most 300 characters; snippets 1200. Fetch important
sources before making factual claims; cite the final source URL.

Fetching supports HTML, `text/*`, JSON and XML. HTML extraction removes scripts,
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
addresses and local hostnames are rejected. DNS results and each redirect are
checked for public addresses; HTTPS downgrades are rejected. DNS preflight and
connection resolution are separate, so this is not DNS pinning or a complete SSRF
sandbox. Stronger guarantees need network isolation. HTTP verifies TLS and does not
inherit proxy/certificate environment settings. Fetching never uses search keys.
Enabled web tools register an original-task experiment blocker because live
responses have no frozen snapshots. Ordinary interactive use remains available.

## Extend and verify offline

| File / public entry | Responsibility |
|---|---|
| [client.py](client.py): `WebClient`, `WebConfig`, `WebError` | HTTP, cache, destinations, cancellation and close |
| [search.py](search.py): `create_web_search_tool` | Brave/Tavily adapters and results |
| [fetch.py](fetch.py): `create_web_fetch_tool` | Text extraction and pagination |
| [registration.py](registration.py): `definitions` | Catalog, credentials and ownership |
| [__init__.py](__init__.py) | Public clients and factories |

Factories borrow a client; direct callers must `await client.close()`.
Tests inject `httpx.MockTransport` and an async `check_url` callback to avoid DNS
and HTTP. Catalog registers client ownership before tool construction; Application
handles failed construction/startup cleanup and shutdown. No ambient keys are read.

```bash
.venv/bin/python -m unittest tests.lab.test_web_tools tests.run.test_web_tools -v
```

Offline tests cover behavior and integration, not live API compatibility, search
quality or model quality. Protocol references:
[Brave Web Search](https://api-dashboard.search.brave.com/api-reference/web/search/get),
[Tavily Search](https://docs.tavily.com/documentation/api-reference/endpoint/search).
