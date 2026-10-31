"""Web tools through Catalog, host permissions and the normal Application."""
import asyncio
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import httpx

from fruitfly_agent.core import AgentLoopConfig
from fruitfly_agent.core.session import Session
from fruitfly_agent.core.tool_runtime.authorization import AuthorizationRequest, ToolPermission
from fruitfly_agent.interactive import AgentApplication
from fruitfly_agent.lab.catalog import AssemblyContext, MechanismSelection, assemble_lab, builtin_catalog, PermissionPolicy
from fruitfly_agent.lab.environment.permissions import PermissionAuthorizer
from fruitfly_agent.lab.tools.web import WebClient
from fruitfly_agent.run import RunApplicationFactory, build_runtime
from fruitfly_agent.run.application import record_session_manifest
from fruitfly_agent.run.configuration import HarnessProfile
from tests.support.faux_provider import FauxProvider
from tests.support.run import _write_catalog


async def public_destination(url):
    return None


class WebAssemblyTests(unittest.IsolatedAsyncioTestCase):
    async def test_configuration_projects_service_credential_names_and_status_without_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_catalog(root / ".fruitfly/models.yaml", {"offline": "offline-model"})
            factory = RunApplicationFactory(cwd=root, environment={})
            configuration = factory.configuration
            configuration.set_mechanism("web-search-tool", enabled=True)
            configuration.set_parameter("web-search-tool", "backend", "deepseek")
            snapshot = configuration.snapshot()
            view = next(m for m in snapshot.mechanisms if m.mechanism_id == "web-search-tool")
            self.assertIn("DEEPSEEK_SEARCH_API_KEY: missing", view.effects)
            self.assertIn("DEEPSEEK_SEARCH_API_KEY", " ".join(snapshot.warnings))
            factory.environment["DEEPSEEK_SEARCH_API_KEY"] = "fixture-private-key"
            snapshot = configuration.snapshot()
            view = next(m for m in snapshot.mechanisms if m.mechanism_id == "web-search-tool")
            self.assertIn("DEEPSEEK_SEARCH_API_KEY: set", view.effects)
            self.assertNotIn("fixture-private-key", repr(snapshot))
            self.assertNotIn("DEEPSEEK_SEARCH_API_KEY", " ".join(snapshot.warnings))

    async def test_optional_registration_and_missing_credential_are_offline(self):
        catalog = builtin_catalog()
        self.assertFalse(any(s.mechanism_id.startswith("web-") for s in catalog.default_selections()))
        names = {"web-search-tool": "web_search", "web-fetch-tool": "web_fetch"}
        for mechanism, tool in names.items():
            definition = catalog.get(mechanism)
            self.assertEqual((tool,), definition.descriptor.effects.tools)
            self.assertTrue(definition.descriptor.effects.uses_network)
            self.assertFalse(definition.descriptor.effects.uses_provider)
            self.assertFalse(definition.descriptor.effects.writes_files)
        with tempfile.TemporaryDirectory() as directory:
            provider = FauxProvider()
            context = AssemblyContext(Path(directory), object(), "offline", Mock())
            with self.assertRaisesRegex(ValueError, "BRAVE_SEARCH_API_KEY"):
                assemble_lab(AgentLoopConfig(provider=provider, model="offline"), catalog=catalog,
                             selections=(MechanismSelection("web-search-tool"),), context=context)
            self.assertEqual([], provider.calls)
            for backend, variable in (("brave", "BRAVE_SEARCH_API_KEY"), ("tavily", "TAVILY_API_KEY"),
                                      ("deepseek", "DEEPSEEK_SEARCH_API_KEY")):
                lookups = []
                def resolve(name):
                    lookups.append(name)
                    return "offline-search-token"
                owned = []
                result = assemble_lab(AgentLoopConfig(provider=provider, model="offline"), catalog=catalog,
                    selections=(MechanismSelection("web-search-tool", parameters={"backend": backend}),),
                    context=replace(context, secret_resolver=resolve, resource_sink=owned))
                client = result.components["web-search-client"]
                self.assertEqual([variable], lookups)
                self.assertIn(client, owned)
                self.assertEqual("web_search", result.config.tools[0].name)
                await client.close()
            # Disabled selections need neither credentials nor HTTP resources.
            result = assemble_lab(AgentLoopConfig(provider=provider, model="offline"), catalog=catalog,
                selections=(MechanismSelection("web-search-tool", enabled=False),), context=context)
            self.assertFalse(any(key.startswith("web-") for key in result.components))

    async def test_deepseek_tools_require_separate_default_keys_offline(self):
        catalog = builtin_catalog()
        with tempfile.TemporaryDirectory() as directory:
            context = AssemblyContext(Path(directory), object(), "offline", Mock())
            for mechanism in ("web-search-tool", "web-fetch-tool"):
                with self.assertRaisesRegex(ValueError, "DEEPSEEK_SEARCH_API_KEY" if mechanism == "web-search-tool" else "DEEPSEEK_FETCH_API_KEY"):
                    assemble_lab(AgentLoopConfig(provider=FauxProvider(), model="offline"), catalog=catalog,
                        selections=(MechanismSelection(mechanism, parameters={"backend": "deepseek"}),), context=context)
            lookups, owned = [], []
            def resolve(name):
                lookups.append(name)
                return "offline-token"
            result = assemble_lab(AgentLoopConfig(provider=FauxProvider(), model="offline"), catalog=catalog,
                selections=tuple(MechanismSelection(name, parameters={"backend": "deepseek"})
                                 for name in ("web-search-tool", "web-fetch-tool")),
                context=replace(context, secret_resolver=resolve, resource_sink=owned))
            self.assertEqual(["DEEPSEEK_SEARCH_API_KEY", "DEEPSEEK_FETCH_API_KEY"], lookups)
            self.assertEqual(["web_search", "web_fetch"], [t.name for t in result.config.tools])
            for client in owned:
                if isinstance(client, WebClient):
                    await client.close()

    async def test_bad_parameters_are_rejected_even_when_disabled(self):
        catalog = builtin_catalog()
        for values in ({"backend": "unknown"}, {"api_key_env": "a key value"},
                       {"timeout_seconds": float("nan")}, {"cache_entries": -1}, {"max_retries": 99}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                catalog.resolve((MechanismSelection("web-search-tool", enabled=False, parameters=values),))

    async def test_host_network_policy_allows_denies_and_audits_without_changing_file_grants(self):
        with tempfile.TemporaryDirectory() as directory:
            for allow in (True, False):
                events = []
                authorizer = PermissionAuthorizer(PermissionPolicy(Path(directory), allow_network=allow), audit=events.append)
                request = AuthorizationRequest("network", "web_search", {"query": "test"}, ToolPermission("network_read"))
                async with authorizer.authorize(request) as decision:
                    self.assertEqual(allow, decision.allowed)
                    with self.assertRaises(PermissionError):
                        authorizer.require_execution()
                self.assertEqual(allow, events[0]["allowed"])
                self.assertNotIn("query", events[0])
                self.assertEqual("allow" if allow else "deny", authorizer.policy.identity()["network_reads"])
                unknown = replace(request, permission=ToolPermission("invented_operation"))
                async with authorizer.authorize(unknown) as decision:
                    self.assertFalse(decision.allowed)
                signal = asyncio.Event()
                signal.set()
                with self.assertRaises(asyncio.CancelledError):
                    async with authorizer.authorize(request, signal=signal):
                        self.fail("cancelled authorization must not yield")

    async def test_host_injects_credentials_without_recording_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model_path = root / ".fruitfly/models.yaml"
            _write_catalog(model_path, {"offline": "offline-model"})
            registry = Mock()
            registry.create.return_value = FauxProvider()
            digests = []
            for token in ("offline-search-token-a", "offline-search-token-b"):
                resources = []
                with Session(root / (token + ".jsonl")) as session:
                    runtime = build_runtime(HarnessProfile("default", str(model_path), "offline", (
                        MechanismSelection("web-search-tool", parameters={"backend": "deepseek", "api_key_env": "CUSTOM_SEARCH_KEY"}),
                        MechanismSelection("web-fetch-tool", parameters={"backend": "deepseek", "api_key_env": "CUSTOM_SEARCH_KEY"}))), config_path=root / "config.yaml", catalog=builtin_catalog(),
                        environment={"CUSTOM_SEARCH_KEY": token}, cwd=root, session=session,
                        provider_registry=registry, resource_sink=resources)
                    manifest = json.dumps(runtime.manifest.to_dict())
                    for resource in resources:
                        if isinstance(resource, WebClient):
                            self.addAsyncCleanup(resource.close)
                    record_session_manifest(session, runtime)
                    self.assertNotIn(token, manifest)
                    self.assertNotIn(token, session.path.read_text())
                    self.assertIn("CUSTOM_SEARCH_KEY", manifest)
                    self.assertEqual(["web_search", "web_fetch"], [t.name for t in runtime.config.tools])
                    digests.append(runtime.manifest.digest)
                    for resource in resources:
                        if isinstance(resource, WebClient):
                            await resource.close()
            self.assertEqual(digests[0], digests[1], "changing a secret value must not serialize it into identity")

    async def test_application_search_then_fetch_and_recovery_uses_fresh_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_catalog(root / ".fruitfly/models.yaml", {"offline": "offline-model"})
            provider, requests, clients = FauxProvider(), [], []
            registry = Mock()
            registry.create.return_value = provider
            def respond(request):
                requests.append(request)
                if request.url.host == "api.search.brave.com":
                    return httpx.Response(200, json={"web": {"results": [
                        {"title": "Official", "url": "https://example.org/requirements", "description": "GPU requirements"}]}})
                self.assertNotIn("x-subscription-token", request.headers)
                self.assertNotIn("authorization", request.headers)
                return httpx.Response(200, text="GPU: 24 GB")
            def create_client(config):
                client = WebClient(config, transport=httpx.MockTransport(respond), check_url=public_destination)
                clients.append(client)
                return client
            factory = RunApplicationFactory(cwd=root, environment={"BRAVE_SEARCH_API_KEY": "offline-search-token"},
                                             provider_registry=registry)
            factory.configuration.set_mechanism("working-memory-reduction", enabled=False)
            for name in ("web-search-tool", "web-fetch-tool"):
                factory.configuration.set_mechanism(name, enabled=True)
            factory.configuration.save()
            factory.reload_configuration()
            app = AgentApplication(factory)
            self.addAsyncCleanup(app.close)
            path = root / ".fruitfly/sessions/web.jsonl"
            with patch("fruitfly_agent.lab.tools.web.registration.WebClient", side_effect=create_client):
                await app.start(session_path=path)
                self.assertEqual([], requests)
                provider.respond_tool_call("web_search", {"query": "GPU requirements", "domains": ["example.org"]})
                provider.respond_tool_call("web_fetch", {"url": "https://example.org/requirements"})
                provider.respond_text("The source says GPU: 24 GB.")
                result = await app.submit("research GPU requirements")
                self.assertFalse(result.is_error)
                messages = [m for m in result.messages if m.role == "toolResult"]
                self.assertEqual(2, len(messages))
                self.assertTrue(all(not m.is_error for m in messages))
                self.assertIn("GPU: 24 GB", messages[-1].text)
                self.assertEqual(2, len(requests))
                await app.close()
                self.assertTrue(all(c._http.is_closed for c in clients))
                await app.start(resume=True, session_path=path)
                provider.respond_tool_call("web_fetch", {"url": "https://example.org/requirements"})
                provider.respond_text("Checked again.")
                await app.submit("check the same source again")
                self.assertEqual(3, len(requests))
                await app.close()
            self.assertNotIn("offline-search-token", path.read_text())

    async def test_application_cleans_client_when_later_assembly_or_startup_fails(self):
        for failure in ("assembly", "startup"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                _write_catalog(root / ".fruitfly/models.yaml", {"offline": "offline-model"})
                registry = Mock()
                registry.create.return_value = FauxProvider()
                clients = []
                def create_client(config):
                    client = WebClient(config, transport=httpx.MockTransport(lambda r: self.fail("construction sent HTTP")))
                    if failure == "startup":
                        async def fail_start():
                            raise ValueError("fixture startup failure")
                        client.start = fail_start
                    clients.append(client)
                    return client
                factory = RunApplicationFactory(cwd=root, environment={}, provider_registry=registry)
                factory.configuration.set_mechanism("web-fetch-tool", enabled=True)
                factory.configuration.save()
                factory.reload_configuration()
                app = AgentApplication(factory)
                self.addAsyncCleanup(app.close)
                def fail_tool(*, service):
                    raise ValueError("fixture assembly failure")
                with patch("fruitfly_agent.lab.tools.web.registration.WebClient", side_effect=create_client):
                    if failure == "assembly":
                        with patch("fruitfly_agent.lab.tools.web.registration.create_web_fetch_tool", side_effect=fail_tool):
                            with self.assertRaisesRegex(ValueError, "fixture assembly"):
                                await app.start()
                    else:
                        with self.assertRaisesRegex(ValueError, "fixture startup"):
                            await app.start()
                self.assertEqual(1, len(clients))
                self.assertTrue(clients[0]._http.is_closed)
