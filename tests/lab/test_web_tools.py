"""Public web tool behavior with no network, credentials or model services."""
import asyncio
import json
import unittest
from unittest.mock import patch

import httpx

from fruitfly_agent.core.tool_runtime import ToolCallContext
from fruitfly_agent.lab.tools.web import WebClient, WebConfig, WebError, create_web_fetch_tool, create_web_search_tool
from fruitfly_agent.lab.tools.web.client import normalize_url, resolve_public_host
from tests.support.faux_provider import FauxProvider
from tests.support.loop import make_config, run_loop


async def public_destination(url):
    return None


def context(name, args, signal=None):
    return ToolCallContext("offline-call", name, args, None, signal=signal)


class WebToolTests(unittest.IsolatedAsyncioTestCase):
    def client(self, handler, **options):
        client = WebClient(WebConfig(**options), transport=httpx.MockTransport(handler), check_url=public_destination)
        self.addAsyncCleanup(client.close)
        return client

    async def test_deepseek_search_maps_summary_filters_and_caches(self):
        requests = []
        def respond(request):
            requests.append(request)
            return httpx.Response(200, json={"results": [
                {"url": "https://docs.example.org/a#part", "title": "<b>Source</b>", "summary": "Detailed evidence", "snippet": "Short"},
                {"url": "https://docs.example.org/a", "title": "Duplicate"},
                {"url": "https://other.org/a", "title": "Excluded"},
            ]})
        tool = create_web_search_tool(self.client(respond), backend="deepseek", api_key="offline-token")
        args = {"query": "GPU", "count": 2, "domains": ["example.org"], "freshness": "week"}
        first = (await tool.execute(context(tool.name, args))).details
        second = (await tool.execute(context(tool.name, args))).details
        self.assertEqual(1, len(requests))
        request = requests[0]
        self.assertEqual("https://api.deepseek.com/v1/tools/search", str(request.url))
        self.assertEqual("POST", request.method)
        self.assertEqual("Bearer offline-token", request.headers["authorization"])
        payload = json.loads(request.content)
        self.assertIn("site:example.org", payload["query"])
        self.assertRegex(payload["query"], r" after:\d{4}-\d{2}-\d{2}$")
        self.assertEqual(2, payload["count"])
        self.assertFalse(payload["need_content"])
        self.assertEqual(1, len(first["results"]))
        self.assertEqual("Detailed evidence", first["results"][0]["snippet"])
        self.assertTrue(second["cached"])

    async def test_deepseek_combined_query_limit_rejects_before_http(self):
        tool = create_web_search_tool(self.client(lambda r: self.fail("unexpected HTTP")),
                                      backend="deepseek", api_key="offline-token")
        for args in ({"query": "x" * 129}, {"query": "x" * 120, "domains": ["example.org"]},
                     {"query": "x" * 120, "freshness": "day"}):
            with self.subTest(args=args), self.assertRaises(WebError) as failure:
                await tool.execute(context(tool.name, args))
            self.assertEqual("invalid_arguments", failure.exception.code)

    async def test_deepseek_fetch_preserves_markdown_paginates_and_reports_source_url(self):
        requests = []
        def respond(request):
            requests.append(request)
            return httpx.Response(200, json={"title": "Docs", "content": "# Heading\n\n  code\n[Guide](https://example.org/guide)"})
        tool = create_web_fetch_tool(self.client(respond), backend="deepseek", api_key="offline-token")
        args = {"url": "https://example.org/start", "limit": 2}
        first = (await tool.execute(context(tool.name, args))).details
        second = (await tool.execute(context(tool.name, {**args, "offset": first["next_offset"]}))).details
        self.assertEqual(1, len(requests))
        self.assertEqual("https://api.deepseek.com/v1/tools/fetch", str(requests[0].url))
        self.assertEqual({"url": args["url"]}, json.loads(requests[0].content))
        self.assertEqual("Bearer offline-token", requests[0].headers["authorization"])
        self.assertEqual("Docs", first["title"])
        self.assertEqual(args["url"], first["url"])
        self.assertIn("L3:   code", second["text"])
        self.assertIn("[Guide](https://example.org/guide)", second["text"])
        self.assertEqual(first["content_id"], second["content_id"])
        self.assertTrue(second["cached"])
        self.assertIsNone(second["next_offset"])

    async def test_deepseek_fetch_rejects_bad_payloads_without_caching_or_leaking_keys(self):
        for body, code in (({}, "invalid_response"), ({"content": 1}, "invalid_response"),
                           ({"content": ""}, "empty_content"), ({"content": "  \n"}, "empty_content"),
                           ({"content": "text", "title": None}, "invalid_response"),
                           ({"error": "offline-token", "content": "text"}, "invalid_response")):
            calls = []
            def respond(request):
                calls.append(request)
                return httpx.Response(200, json=body)
            tool = create_web_fetch_tool(self.client(respond), backend="deepseek", api_key="offline-token")
            for _ in range(2):
                with self.subTest(body=body), self.assertRaises(WebError) as failure:
                    await tool.execute(context(tool.name, {"url": "https://example.org/"}))
                self.assertEqual(code, failure.exception.code)
                self.assertNotIn("offline-token", str(failure.exception))
            self.assertEqual(2, len(calls))

    async def test_deepseek_fetch_rejects_private_source_urls_before_http(self):
        tool = create_web_fetch_tool(self.client(lambda r: self.fail("unexpected HTTP")),
                                     backend="deepseek", api_key="offline-token")
        for url in ("file:///etc/passwd", "http://127.0.0.1/", "https://user:password@example.org/"):
            with self.subTest(url=url), self.assertRaises(WebError):
                await tool.execute(context(tool.name, {"url": url}))

    async def test_brave_filters_deduplicates_bounds_and_caches_sources(self):
        requests = []
        def respond(request):
            requests.append(request)
            return httpx.Response(200, json={"web": {"results": [
                {"title": "<b>Official</b>", "url": "https://docs.example.org/guide#part", "description": "x" * 3000},
                {"title": "Duplicate", "url": "https://docs.example.org/guide", "description": "same"},
                {"title": "Other", "url": "https://other.org/", "description": "filtered"},
                {"title": "Private", "url": "http://127.0.0.1/", "description": "filtered"},
            ]}})
        client = self.client(respond)
        tool = create_web_search_tool(client, api_key="offline-token")
        args = {"query": "terminal bench GPU", "domains": ["example.org"], "freshness": "month"}
        first = (await tool.execute(context(tool.name, args))).details
        second = (await tool.execute(context(tool.name, args))).details
        self.assertEqual(1, len(requests))
        self.assertEqual("offline-token", requests[0].headers["x-subscription-token"])
        self.assertNotIn("offline-token", str(requests[0].url))
        self.assertIn("site:example.org", requests[0].url.params["q"])
        self.assertEqual("pm", requests[0].url.params["freshness"])
        self.assertEqual(1, len(first["results"]))
        self.assertEqual("Official", first["results"][0]["title"])
        self.assertEqual(1200, len(first["results"][0]["snippet"]))
        self.assertEqual("https://docs.example.org/guide", first["results"][0]["url"])
        self.assertFalse(first["cached"])
        self.assertTrue(second["cached"])
        self.assertEqual(first["retrieved_at"], second["retrieved_at"])
        self.assertNotIn("offline-token", json.dumps(first))

    async def test_tavily_uses_bounded_basic_search_without_generated_answer(self):
        requests = []
        def respond(request):
            requests.append(request)
            return httpx.Response(200, json={"results": [{"url": "https://example.org/a", "title": "Source", "content": "Evidence"}]})
        tool = create_web_search_tool(self.client(respond), backend="tavily", api_key="offline-token")
        result = (await tool.execute(context(tool.name, {"query": "GPU", "count": 2, "freshness": "week", "domains": ["example.org"]}))).details
        payload = json.loads(requests[0].content)
        self.assertEqual("POST", requests[0].method)
        self.assertEqual("Bearer offline-token", requests[0].headers["authorization"])
        self.assertEqual("basic", payload["search_depth"])
        self.assertEqual("week", payload["time_range"])
        self.assertEqual(2, payload["max_results"])
        self.assertFalse(payload["include_answer"])
        self.assertFalse(payload["include_raw_content"])
        self.assertNotIn("api_key", payload)
        self.assertEqual("Evidence", result["results"][0]["snippet"])

    async def test_no_results_and_invalid_responses_are_distinct(self):
        for backend, body, succeeds in (
            ("brave", {"query": {"original": "unmatched"}}, True),
            ("tavily", {"results": []}, True),
            ("deepseek", {"results": []}, True),
            ("deepseek", {"results": [{"url": "https://example.org/", "snippet": "Fallback"}]}, True),
            ("deepseek", {"error": "offline-token"}, False),
            ("brave", {}, False), ("brave", {"web": {"results": {}}}, False),
            ("tavily", {"results": [{"title": "no url"}]}, False),
            ("tavily", {"error": "offline-token"}, False),
        ):
            with self.subTest(backend=backend, body=body):
                calls = []
                def respond(request):
                    calls.append(request)
                    return httpx.Response(200, json=body)
                tool = create_web_search_tool(self.client(respond), backend=backend, api_key="offline-token")
                if succeeds:
                    results = (await tool.execute(context(tool.name, {"query": "unmatched"}))).details["results"]
                    self.assertEqual(len(body.get("results", [])), len(results))
                    if results:
                        self.assertEqual("Fallback", results[0]["snippet"])
                else:
                    for _ in range(2):
                        with self.assertRaises(WebError) as failure:
                            await tool.execute(context(tool.name, {"query": "unmatched"}))
                        self.assertEqual("invalid_response", failure.exception.code)
                        self.assertNotIn("offline-token", str(failure.exception))
                    self.assertEqual(2, len(calls), "rejected responses must not remain in cache")

    async def test_fetch_extracts_title_links_code_tables_and_pages(self):
        requests = []
        def respond(request):
            requests.append(request)
            return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, text="""
                <html><head><title>Official &amp; Docs</title><style>hidden style</style></head>
                <body><script>hidden code</script><h1>GPU requirements</h1>
                <p>Read <a href="/guide">the guide</a>.</p><pre>  preserve indent\nnext line</pre>
                <table><tr><th>GPU</th><td>24 GB</td></tr></table></body></html>""")
        tool = create_web_fetch_tool(self.client(respond))
        first = (await tool.execute(context(tool.name, {"url": "https://example.org/start", "limit": 2}))).details
        second = (await tool.execute(context(tool.name, {"url": "https://example.org/start", "offset": first["next_offset"]}))).details
        self.assertEqual("Official & Docs", first["title"])
        self.assertIn("https://example.org/guide", first["text"])
        self.assertNotIn("hidden", first["text"] + second["text"])
        self.assertIn("  preserve indent", second["text"])
        self.assertIn("24 GB", second["text"])
        self.assertTrue(first["truncated"])
        self.assertFalse(second["truncated"])
        self.assertEqual(first["content_id"], second["content_id"])
        self.assertEqual(first["source_id"], second["source_id"])
        self.assertEqual(1, len(requests))
        self.assertTrue(second["cached"])
        self.assertIsNone(second["next_offset"])

    async def test_every_character_of_a_long_line_can_be_retrieved(self):
        text = "a" * 21_000 + "END"
        tool = create_web_fetch_tool(self.client(lambda r: httpx.Response(200, text=text)))
        offset, recovered = 1, []
        while offset is not None:
            result = (await tool.execute(context(tool.name, {"url": "https://example.org/", "offset": offset, "limit": 200}))).details
            self.assertLessEqual(len(result["text"]), 20_000)
            recovered.extend(line.split(": ", 1)[1] for line in result["text"].splitlines())
            offset = result["next_offset"]
        self.assertEqual(text, "".join(recovered))

    async def test_unsupported_empty_and_invalid_offset_fail_clearly(self):
        for media, body, args, expected in (
            ("application/pdf", b"%PDF-1.7", {}, "unsupported_content"),
            ("application/octet-stream", b"binary", {}, "unsupported_content"),
            ("text/plain", b"a\x00b", {}, "unsupported_content"),
            ("text/html", b"<script>only script</script>", {}, "empty_content"),
            ("text/plain", b"one", {"offset": 2}, "invalid_offset"),
        ):
            with self.subTest(media=media, expected=expected):
                tool = create_web_fetch_tool(self.client(lambda r: httpx.Response(200, headers={"content-type": media}, content=body)))
                with self.assertRaises(WebError) as failure:
                    await tool.execute(context(tool.name, {"url": "https://example.org/", **args}))
                self.assertEqual(expected, failure.exception.code)

    async def test_bad_arguments_do_not_send_http(self):
        def unexpected(request):
            self.fail("invalid arguments must fail before network access")
        client = self.client(unexpected)
        tools = (create_web_fetch_tool(client), create_web_search_tool(client, api_key="offline-token"))
        for tool, args in (
            (tools[0], {"url": "file:///etc/passwd"}), (tools[0], {"url": "http://127.0.0.1"}),
            (tools[0], {"url": "https://example.org", "limit": 201}),
            (tools[1], {"query": " "}), (tools[1], {"query": "x" * 501}),
            (tools[1], {"query": "x", "count": True}),
            (tools[1], {"query": "x", "domains": ["https://example.org"]}),
            (tools[1], {"query": "x", "freshness": "forever"}),
        ):
            with self.subTest(args=args), self.assertRaises(WebError):
                await tool.execute(context(tool.name, args))

    async def test_errors_become_failed_core_tool_messages_without_secrets(self):
        client = self.client(lambda r: httpx.Response(401, text="offline-token"), max_retries=0)
        tool = create_web_search_tool(client, api_key="offline-token")
        provider = FauxProvider()
        provider.respond_tool_call(tool.name, {"query": "GPU"})
        provider.respond_text("The search credential was rejected.")
        result = await run_loop(make_config(provider, [tool]), "research")
        message = result.messages[-2]
        self.assertTrue(message.is_error)
        self.assertIn('"code": "authentication"', message.text)
        self.assertNotIn("offline-token", message.text)


class HttpBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def client(self, handler, **options):
        client = WebClient(WebConfig(**options), transport=httpx.MockTransport(handler), check_url=public_destination)
        self.addAsyncCleanup(client.close)
        return client

    async def test_transient_retry_is_bounded_but_permanent_errors_never_retry(self):
        for status, expected_attempts, expected in ((503, 2, "http_error"), (429, 2, "rate_limit"),
                                                   (401, 1, "authentication"), (403, 1, "forbidden"),
                                                   (404, 1, "not_found"), (402, 1, "quota_exceeded"), (432, 1, "quota_exceeded")):
            with self.subTest(status=status):
                calls = []
                def respond(request):
                    calls.append(request)
                    return httpx.Response(status, text="do not expose upstream secrets")
                client = self.client(respond)
                with self.assertRaises(WebError) as failure:
                    await client.request("GET", "https://example.org/")
                self.assertEqual(expected, failure.exception.code)
                self.assertEqual(expected_attempts, len(calls))
                self.assertNotIn("upstream secrets", str(failure.exception))

    async def test_retry_success_is_cached_and_cache_expires_and_is_scoped(self):
        calls, now = [], [0.0]
        def respond(request):
            calls.append(request)
            return httpx.Response(503 if len(calls) == 1 else 200, text="source")
        client = WebClient(WebConfig(cache_ttl_seconds=5, cache_entries=1), transport=httpx.MockTransport(respond),
                           check_url=public_destination, clock=lambda: now[0])
        self.addAsyncCleanup(client.close)
        _, cached = await client.request("GET", "https://example.org/a", headers={"Authorization": "one"})
        self.assertFalse(cached)
        self.assertEqual(2, len(calls))
        self.assertTrue((await client.request("GET", "https://example.org/a", headers={"Authorization": "one"}))[1])
        now[0] = 6
        self.assertFalse((await client.request("GET", "https://example.org/a", headers={"Authorization": "one"}))[1])
        self.assertFalse((await client.request("GET", "https://example.org/a", headers={"Authorization": "two"}))[1])
        await client.request("GET", "https://example.org/b")
        self.assertFalse((await client.request("GET", "https://example.org/a", headers={"Authorization": "two"}))[1])

    async def test_redirects_are_checked_and_search_authentication_is_not_forwarded(self):
        calls = []
        def respond(request):
            calls.append(request)
            return httpx.Response(302, headers={"location": "https://other.org/target"})
        client = self.client(respond)
        with self.assertRaises(WebError) as failure:
            await client.request("GET", "https://example.org/", headers={"Authorization": "offline-token"})
        self.assertEqual("redirect_blocked", failure.exception.code)
        self.assertEqual(1, len(calls))
        for location, expected in (("http://127.0.0.1/", "invalid_url"),
                                   ("http://example.org/", "redirect_blocked")):
            client = self.client(lambda r: httpx.Response(302, headers={"location": location}))
            with self.assertRaises(WebError) as failure:
                await client.request("GET", "https://example.org/", redirects=True)
            self.assertEqual(expected, failure.exception.code)

    async def test_redirect_limit_and_final_url(self):
        checked = []
        async def check(url):
            checked.append(url)
        client = self.client(lambda r: httpx.Response(302, headers={"location": "/next"}), max_redirects=1)
        with self.assertRaises(WebError) as failure:
            await client.request("GET", "https://example.org/", redirects=True)
        self.assertEqual("redirect_limit", failure.exception.code)
        def respond(request):
            return httpx.Response(302, headers={"location": "/final"}) if request.url.path == "/" else httpx.Response(200, text="done")
        client = WebClient(transport=httpx.MockTransport(respond), check_url=check)
        self.addAsyncCleanup(client.close)
        result, _ = await client.request("GET", "https://example.org/", redirects=True)
        self.assertEqual("https://example.org/final", result.url)
        self.assertEqual(["https://example.org/", "https://example.org/final"], checked)

    async def test_response_stream_limit_closes_stream(self):
        closed = []
        class Stream(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b"a" * 20_000
                yield b"b" * 20_000
            async def aclose(self):
                closed.append(True)
        client = self.client(lambda r: httpx.Response(200, stream=Stream()), max_response_bytes=20_000)
        with self.assertRaises(WebError) as failure:
            await client.request("GET", "https://example.org/")
        self.assertEqual("response_too_large", failure.exception.code)
        self.assertEqual([True], closed)

    async def test_stalled_body_and_retry_backoff_share_the_total_deadline(self):
        closed, attempts = [], []
        class Stream(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b"a"
                await asyncio.Event().wait()
            async def aclose(self):
                closed.append(True)
        client = self.client(lambda r: httpx.Response(200, stream=Stream()), timeout_seconds=.02)
        with self.assertRaises(WebError) as failure:
            await client.request("GET", "https://example.org/")
        self.assertEqual("timeout", failure.exception.code)
        self.assertEqual([True], closed)
        def unavailable(request):
            attempts.append(request)
            return httpx.Response(503)
        client = self.client(unavailable, timeout_seconds=.02, max_retries=2)
        with self.assertRaises(WebError) as failure:
            await client.request("GET", "https://example.org/")
        self.assertEqual("timeout", failure.exception.code)
        self.assertEqual(1, len(attempts), "the retry backoff must not extend the deadline")

    async def test_queued_cancellation_sends_no_extra_request(self):
        entered, calls, signal = asyncio.Event(), [], asyncio.Event()
        async def stalled(request):
            calls.append(request)
            entered.set()
            await asyncio.Event().wait()
        client = self.client(stalled)
        first = asyncio.create_task(client.request("GET", "https://example.org/first"))
        try:
            await entered.wait()
            second = asyncio.create_task(client.request("GET", "https://example.org/second", signal=signal))
            signal.set()
            with self.assertRaises(asyncio.CancelledError):
                await second
            self.assertEqual(1, len(calls))
        finally:
            first.cancel()
            await asyncio.gather(first, return_exceptions=True)

    async def test_fetch_never_replays_response_cookies(self):
        cookies = []
        def respond(request):
            cookies.append(request.headers.get("cookie", ""))
            return httpx.Response(200, headers={"set-cookie": "session=offline-value; Path=/"}, text="public page")
        client = self.client(respond, cache_entries=0)
        tool = create_web_fetch_tool(client)
        for path in ("first", "second"):
            await tool.execute(context(tool.name, {"url": "https://example.org/" + path}))
        self.assertEqual(["", ""], cookies)

    async def test_total_deadline_interrupts_a_stalled_request(self):
        cancelled = asyncio.Event()
        async def stalled(request):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        client = self.client(stalled, timeout_seconds=.02)
        with self.assertRaises(WebError) as failure:
            await client.request("GET", "https://example.org/")
        self.assertEqual("timeout", failure.exception.code)
        self.assertTrue(cancelled.is_set())

    async def test_signal_and_task_cancellation_interrupt_http_without_retry(self):
        for use_signal in (True, False):
            with self.subTest(signal=use_signal):
                entered, exited, signal = asyncio.Event(), asyncio.Event(), asyncio.Event()
                async def stalled(request):
                    entered.set()
                    try:
                        await asyncio.Event().wait()
                    finally:
                        exited.set()
                client = self.client(stalled)
                task = asyncio.create_task(client.request("GET", "https://example.org/", signal=signal))
                await entered.wait()
                signal.set() if use_signal else task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                self.assertTrue(exited.is_set())
                # The queue lock is released on every cancellation path.
                signal.set()
                with self.assertRaises(asyncio.CancelledError):
                    await client.request("GET", "https://example.org/", signal=signal)

    async def test_dns_checks_reject_private_and_mixed_destinations(self):
        loop = asyncio.get_running_loop()
        for addresses, succeeds in ((["93.184.216.34"], True), (["127.0.0.1"], False),
                                    (["93.184.216.34", "10.0.0.1"], False), (["::1"], False)):
            records = [(2, 1, 6, "", (value, 443)) for value in addresses]
            with self.subTest(addresses=addresses), patch.object(loop, "getaddrinfo", return_value=records):
                if succeeds:
                    await resolve_public_host("https://example.org/")
                else:
                    with self.assertRaises(WebError) as failure:
                        await resolve_public_host("https://example.org/")
                    self.assertEqual("blocked_url", failure.exception.code)

    def test_url_and_budget_validation(self):
        for url in ("file:///etc/passwd", "http://localhost/", "http://127.0.0.1/", "http://[::1]/",
                    "http://user:password@example.org", "https://example.org:8080/", "https://example.org/a\nb"):
            with self.subTest(url=url), self.assertRaises(WebError):
                normalize_url(url)
        self.assertEqual("https://example.org/", normalize_url("https://example.org#part"))
        self.assertEqual("https://93.184.216.34/", normalize_url("https://93.184.216.34/"))
        for options in ({"timeout_seconds": float("nan")}, {"max_retries": 3}, {"cache_entries": -1},
                        {"max_redirects": True}, {"max_response_bytes": 0}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                WebConfig(**options)
