"""RLM/IPython mechanism tests; all Provider behavior is offline."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fruitfly_agent.core import AgentLoopConfig
from fruitfly_agent.core.data_model import UserMessage
from fruitfly_agent.core.loop import run_agent_loop
from fruitfly_agent.core.context import ContextFrame
from fruitfly_agent.lab.catalog import (
    AssemblyContext,
    MechanismSelection,
    ProviderBinding,
    assemble_lab,
    builtin_catalog,
)
from fruitfly_agent.lab.context_manager.externalization.programmatic_context import (
    ProgrammaticContextExternalizer,
    IpythonRuntime,
    ModelQueryBroker,
    ModelQueryConfig,
    SessionArtifactStore,
)
from tests.support.faux_provider import FauxProvider


class SessionArtifactStoreTest(unittest.TestCase):
    def test_content_artifacts_are_addressed_searched_and_integrity_checked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SessionArtifactStore(Path(tmp), max_artifact_bytes=10_000)
            artifact = store.put_text(
                "alpha\nNeedle in context\nomega",
                origin="test",
            )

            self.assertTrue(artifact.reference.startswith("context://sha256/"))
            self.assertEqual("Needle", store.read(artifact.reference, offset=6, limit=6))
            self.assertEqual(1, len(store.search(artifact.reference, "needle")))
            self.assertEqual([artifact], store.list())

            object_path = store.objects / f"{artifact.sha256}.txt"
            object_path.write_text("tampered", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "integrity"):
                store.stat(artifact.reference)

    def test_explicit_json_state_survives_new_store_instance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = SessionArtifactStore(root, max_artifact_bytes=10_000)
            first.save_state("progress", {"cursor": 12, "done": ["a"]})

            second = SessionArtifactStore(root, max_artifact_bytes=10_000)
            self.assertEqual(
                {"cursor": 12, "done": ["a"]},
                second.load_state("progress"),
            )
            self.assertEqual(["progress"], second.list_states())


class ProgrammaticContextExternalizerTest(unittest.TestCase):
    def test_projection_offloads_large_text_without_mutating_canonical_message(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SessionArtifactStore(Path(tmp), max_artifact_bytes=10_000)
            externalizer = ProgrammaticContextExternalizer(
                store,
                threshold_chars=8,
            )
            message = UserMessage(content="large canonical value")
            frame = ContextFrame(
                system_prompt="",
                messages=(message,),
                tools=(),
                model="model",
                max_tokens=100,
            )

            transformed = externalizer.transform(frame)

            self.assertEqual("large canonical value", message.content)
            projected = transformed.frame.messages[0]
            self.assertIn("context://sha256/", projected.content)
            reference_line = next(
                line
                for line in projected.content.splitlines()
                if line.startswith("reference: ")
            )
            reference = reference_line.removeprefix("reference: ")
            self.assertEqual("large canonical value", store.read(reference))


class ModelQueryBrokerTest(unittest.IsolatedAsyncioTestCase):
    async def test_query_is_text_only_and_enforces_call_budget(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            provider = FauxProvider()
            provider.respond_text("child result")
            broker = ModelQueryBroker(
                provider,
                model="child-model",
                profile="child-profile",
                store=SessionArtifactStore(Path(tmp), max_artifact_bytes=10_000),
                config=ModelQueryConfig(
                    max_calls=1,
                    max_concurrent=1,
                    max_input_chars=100,
                    max_output_tokens=20,
                    max_total_tokens=100,
                    max_inline_result_chars=100,
                    timeout_seconds=5,
                ),
            )

            result = await broker.handle(
                "model.query",
                {"prompt": "solve this", "max_output_tokens": 10},
            )

            self.assertEqual("child result", result["text"])
            self.assertEqual("child-profile", result["model_profile"])
            self.assertEqual([], provider.calls[0]["tools"])
            self.assertEqual(10, provider.calls[0]["max_tokens"])
            with self.assertRaisesRegex(RuntimeError, "call budget exhausted"):
                await broker.handle("model.query", {"prompt": "again"})


class IpythonRuntimeTest(unittest.IsolatedAsyncioTestCase):
    async def test_namespace_context_model_bridge_and_explicit_resume_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = SessionArtifactStore(root / "artifacts", max_artifact_bytes=50_000)

            async def host_handler(request_type, payload, signal):
                self.assertEqual("model.query", request_type)
                return {"text": f"answer:{payload['prompt']}"}

            runtime = IpythonRuntime(
                cwd=root,
                artifact_store=store,
                host_handler=host_handler,
                max_output_chars=10_000,
                timeout_seconds=10,
            )
            try:
                from unittest.mock import patch
                with patch.dict('os.environ', {'TEST_PROVIDER_KEY': 'offline-placeholder'}):
                    absent_key = await runtime.execute("import os; 'TEST_PROVIDER_KEY' in os.environ")
                first = await runtime.execute("value = 40")
                persisted = await runtime.execute("value + 2")
                queried = await runtime.execute("await llm_query('subproblem')")
                saved = await runtime.execute(
                    "context.save_state('checkpoint', {'value': value})"
                )
            finally:
                await runtime.close()

            self.assertEqual("False", absent_key.result)
            self.assertEqual("ok", first.status)
            self.assertEqual("42", persisted.result)
            self.assertIn("answer:subproblem", queried.result)
            self.assertEqual("ok", saved.status)

            resumed = IpythonRuntime(
                cwd=root,
                artifact_store=store,
                host_handler=host_handler,
                max_output_chars=10_000,
                timeout_seconds=10,
            )
            try:
                loaded = await resumed.execute("context.load_state('checkpoint')")
                missing_live_value = await resumed.execute("value")
            finally:
                await resumed.close()

            self.assertIn("'value': 40", loaded.result)
            self.assertEqual("error", missing_live_value.status)
            self.assertEqual("NameError", missing_live_value.error["type"])


class RlmAssemblyTest(unittest.TestCase):
    def test_ipython_tool_can_run_without_externalization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            main = FauxProvider()
            child = FauxProvider()
            resolver_calls: list[tuple[str | None, int | None]] = []

            def resolve(profile, max_tokens):
                resolver_calls.append((profile, max_tokens))
                return ProviderBinding(child, "child-model", "child-profile")

            result = assemble_lab(
                AgentLoopConfig(provider=main, model="main-model"),
                catalog=builtin_catalog(),
                selections=(MechanismSelection("ipython-tool"),),
                context=AssemblyContext(
                    workspace=root,
                    session=object(),
                    main_model="main-model",
                    provider_resolver=resolve,
                    session_path=root / "session.jsonl",
                ),
            )

            self.assertEqual(("ipython-tool",), result.mechanism_ids)
            self.assertEqual(["ipython"], [tool.name for tool in result.config.tools])
            self.assertIn("Persistent IPython workspace", result.config.system_prompt)
            self.assertIs(result.config.provider, main)
            self.assertIsNone(result.context_pipeline)
            self.assertIn("ipython-tool", result.components)
            self.assertEqual([(None, 4096)], resolver_calls)

    def test_rlm_reuses_single_ipython_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            child = FauxProvider()
            resolver_calls = []

            def resolve(profile, max_tokens):
                resolver_calls.append((profile, max_tokens))
                return ProviderBinding(child, "child-model", "child-profile")

            context = AssemblyContext(
                workspace=root, session=object(), main_model="main-model",
                provider_resolver=resolve, session_path=root / "session.jsonl",
            )
            with self.assertRaisesRegex(ValueError, "requires: ipython-tool"):
                assemble_lab(
                    AgentLoopConfig(provider=FauxProvider(), model="main-model"),
                    catalog=builtin_catalog(),
                    selections=(MechanismSelection("rlm-ipython"),),
                    context=context,
                )
            result = assemble_lab(
                AgentLoopConfig(provider=FauxProvider(), model="main-model"),
                catalog=builtin_catalog(),
                selections=(MechanismSelection("ipython-tool"), MechanismSelection("rlm-ipython")),
                context=context,
            )
            self.assertEqual(["ipython"], [tool.name for tool in result.config.tools])
            self.assertEqual(("rlm-ipython",), result.context_pipeline.profile.externalization)
            self.assertIn("ipython-tool", result.components)
            self.assertNotIn("rlm-ipython", result.components)
            self.assertEqual([(None, 4096)], resolver_calls)


class StandaloneIpythonToolTest(unittest.IsolatedAsyncioTestCase):
    async def test_selected_tool_executes_without_context_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = assemble_lab(
                AgentLoopConfig(provider=FauxProvider(), model="main-model"),
                catalog=builtin_catalog(),
                selections=(MechanismSelection("ipython-tool"),),
                context=AssemblyContext(
                    workspace=root, session=object(), main_model="main-model",
                    provider_resolver=lambda *_: ProviderBinding(
                        FauxProvider(), "child-model", "child-profile"
                    ),
                    session_path=root / "session.jsonl",
                ),
            )
            component = result.components["ipython-tool"]
            try:
                await component.start()
                first = await component.runtime.execute("value = 40")
                second = await component.runtime.execute("value + 2")
            finally:
                await component.close()
            self.assertIsNone(result.context_pipeline)
            self.assertEqual("ok", first.status)
            self.assertEqual("42", second.result)


class RlmPipelineTest(unittest.IsolatedAsyncioTestCase):
    async def test_externalization_runs_before_reduction_budget_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            main = FauxProvider()
            main.respond_text("done")
            child = FauxProvider()

            result = assemble_lab(
                AgentLoopConfig(
                    provider=main,
                    model="main-model",
                    context_window=5_000,
                    max_tokens=500,
                ),
                catalog=builtin_catalog(),
                selections=(
                    MechanismSelection(
                        "compaction",
                        parameters={},
                    ),
                    MechanismSelection(
                        "rlm-ipython",
                        parameters={"offload_threshold_chars": 1_000},
                    ),
                    MechanismSelection("ipython-tool"),
                ),
                context=AssemblyContext(
                    workspace=root,
                    session=object(),
                    main_model="main-model",
                    provider_resolver=lambda *_: ProviderBinding(
                        child, "child-model", "child-profile"
                    ),
                    session_path=root / "session.jsonl",
                ),
            )
            original = UserMessage(content="large " * 20_000)

            outcome = await run_agent_loop(
                result.config,
                [original],
                context_pipeline=result.context_pipeline,
            )

            self.assertFalse(outcome.is_error, outcome.error_details)
            self.assertEqual(original, outcome.canonical_messages[0])
            projected = main.calls[0]["messages"][0]
            self.assertIn("context://sha256/", projected.content)
            self.assertIn("context://sha256/", outcome.messages[0].content)


if __name__ == "__main__":
    unittest.main()
