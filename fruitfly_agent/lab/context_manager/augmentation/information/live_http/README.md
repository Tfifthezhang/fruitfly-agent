# Live HTTP

[Up: Information Spaces](../README.md)

Fetch current information from an explicitly configured HTTPS text service. Each query sends the user's question to that service and may incur service charges.

| Setting / rule | Behavior |
|---|---|
| Enable | **Context Manager → Live HTTP**; disabled by default |
| `endpoint` | HTTPS URL containing exactly one `{query}`; no credentials or fragment |
| `timeout_seconds` | 5 seconds by default |
| Redirects | Disabled |
| Response | `text/plain` or `application/json`, up to 64 KB |
| State | No response cache or built-in authentication |
| API | `LiveHttpRetriever`, `create_live_http_space(endpoint, timeout=5.0, fetch=None)` |

Inject `fetch` for offline checks. Keep credentials out of URLs and metadata. There are no module-specific environment variables. Cancelling an await does not stop the worker thread; the I/O timeout is not a whole-operation deadline.

Extensions follow [Information source contracts](../README.md#extend-a-source) and must preserve declared destination, encoding, redirect, type, and size behavior.

```bash
.venv/bin/python -m unittest tests.lab.test_information_sources.InformationSourcesTest.test_live_source_fetches_query_on_demand_and_is_read_only -v
```
