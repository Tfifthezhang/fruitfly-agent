"""Service injection and registry extension without tool or transport changes."""
import asyncio
from pathlib import Path
import unittest
from unittest.mock import patch

import httpx

from fruitfly_agent.core import AgentLoopConfig
from fruitfly_agent.core.tool_runtime import ToolCallContext
from fruitfly_agent.lab.catalog import AssemblyContext, LabCatalog, MechanismSelection, assemble_lab
from fruitfly_agent.lab.tools.web import (
    FetchResponse, SearchHit, SearchResponse, WebClient, WebServiceDefinition, WebServiceRegistry,
    create_web_fetch_tool, create_web_search_tool, default_service_registry,
)
from fruitfly_agent.lab.tools.web.registration import definitions
from fruitfly_agent.lab.tools.web.services.deepseek import DeepSeekFetch
from fruitfly_agent.lab.tools.web.services.direct import DirectFetch
from tests.support.faux_provider import FauxProvider


class FixtureSearch:
    name = "fixture"
    max_query_chars = 80
    query_description = "Fixture query."

    def __init__(self):
        self.requests = []

    async def search(self, request, *, signal=None):
        self.requests.append((request, signal))
        return SearchResponse((
            SearchHit("<b>Source</b>", "https://docs.example.org/a#part", "Evidence"),
            SearchHit("Duplicate", "https://docs.example.org/a", "Duplicate"),
            SearchHit("Excluded", "https://other.org/a", "Other"),
        ), 123.0, True)


class FixtureFetch:
    description = "Fixture page reader."

    async def fetch(self, url, *, signal=None):
        self.request = url, signal
        return FetchResponse("Source", "first\nsecond\nthird", url, "https://example.org/final", "fixture-body", 123.0)


class ServiceInjectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_uses_injected_contract_and_still_filters_and_deduplicates(self):
        service, signal = FixtureSearch(), asyncio.Event()
        with patch("fruitfly_agent.lab.tools.web.search.default_service_registry", side_effect=AssertionError("vendor lookup")):
            tool = create_web_search_tool(service=service)
        result = (await tool.execute(ToolCallContext("call", tool.name,
            {"query": " topic ", "domains": ["example.org"], "freshness": "week"}, None, signal=signal))).details
        self.assertEqual("fixture", result["backend"])
        self.assertEqual(1, len(result["results"]))
        self.assertEqual("Source", result["results"][0]["title"])
        request, received_signal = service.requests[0]
        self.assertEqual(("topic", 5, ("example.org",), "week"),
                         (request.query, request.count, request.domains, request.freshness))
        self.assertIs(signal, received_signal)
        self.assertEqual(80, tool.parameters["properties"]["query"]["maxLength"])
        self.assertTrue(result["cached"])

    async def test_fetch_uses_injected_contract_and_common_pagination(self):
        service, signal = FixtureFetch(), asyncio.Event()
        with patch("fruitfly_agent.lab.tools.web.fetch.default_service_registry", side_effect=AssertionError("vendor lookup")):
            tool = create_web_fetch_tool(service=service)
        result = (await tool.execute(ToolCallContext("call", tool.name,
            {"url": "https://example.org/start", "offset": 2, "limit": 1}, None, signal=signal))).details
        self.assertEqual("L2: second", result["text"])
        self.assertEqual(3, result["next_offset"])
        self.assertEqual("https://example.org/final", result["url"])
        self.assertEqual("fixture-body", result["content_id"])
        self.assertEqual(("https://example.org/start", signal), service.request)

    async def test_adapters_expose_known_and_unknown_final_url_without_http_types(self):
        async def public(url):
            pass
        for adapter, expected in ((DirectFetch, "https://example.org/final"), (DeepSeekFetch, None)):
            def respond(request):
                if request.url.host == "api.deepseek.com":
                    return httpx.Response(200, json={"title": "Source", "content": "# Markdown"})
                if request.url.path == "/start":
                    return httpx.Response(302, headers={"location": "/final"})
                return httpx.Response(200, text="source")
            client = WebClient(transport=httpx.MockTransport(respond), check_url=public)
            self.addAsyncCleanup(client.close)
            page = await adapter(client, "fixture-key").fetch("https://example.org/start")
            self.assertIsInstance(page, FetchResponse)
            self.assertEqual(expected, page.final_url)
            self.assertEqual("https://example.org/start", page.source_url)

    async def test_new_service_only_needs_definition_and_factory(self):
        base = default_service_registry()
        service, received_keys = FixtureSearch(), []
        def factory(client, key):
            received_keys.append(key)
            return service
        registry = WebServiceRegistry(
            search=tuple(base.get("search", name) for name in base.choices("search")) +
                   (WebServiceDefinition("fixture", factory, "FIXTURE_WEB_KEY"),),
            fetch=tuple(base.get("fetch", name) for name in base.choices("fetch")))
        catalog = LabCatalog(definitions(registry))
        selection = MechanismSelection("web-search-tool", parameters={"backend": "fixture"})
        with patch("fruitfly_agent.lab.tools.web.registration.WebClient") as create_client:
            self.assertEqual(("FIXTURE_WEB_KEY",), catalog.required_credentials((selection,)))
            create_client.assert_not_called()
        owned = []
        context = AssemblyContext(Path.cwd(), object(), "offline", lambda *args: None,
                                  secret_resolver=lambda name: "fixture-token", resource_sink=owned)
        result = assemble_lab(AgentLoopConfig(provider=FauxProvider()), catalog=catalog,
                              selections=(selection,), context=context)
        self.assertEqual(["fixture-token"], received_keys)
        tool = result.config.tools[0]
        output = (await tool.execute(ToolCallContext("call", tool.name, {"query": "topic"}, None))).details
        self.assertEqual("fixture", output["backend"])
        for resource in owned:
            if isinstance(resource, WebClient):
                await resource.close()

    def test_registry_rejects_unknown_duplicate_and_invalid_credential_names(self):
        definition = WebServiceDefinition("fixture", lambda client, key: FixtureSearch(), "FIXTURE_WEB_KEY")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            WebServiceRegistry(search=(definition, definition))
        with self.assertRaisesRegex(ValueError, "unknown"):
            default_service_registry().get("fetch", "brave")
        with self.assertRaisesRegex(ValueError, "environment variable"):
            definition.credential_variable("an actual key value")
        self.assertEqual("CUSTOM_WEB_KEY", definition.credential_variable("CUSTOM_WEB_KEY"))
        self.assertEqual("", default_service_registry().get("fetch", "direct").credential_variable("UNUSED"))
