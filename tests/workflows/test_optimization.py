"""Offline end-to-end optimizer selection, inbox, and next-session adoption."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch, AsyncMock

from fruitfly_agent.interactive import AgentApplication
from fruitfly_agent.core.model_stream import AssistantMessageEventStream
from fruitfly_agent.run.application import RunApplicationFactory
from fruitfly_agent.run.configuration import load_harness_config
from fruitfly_agent.lab.optimization.tasks import load_task_cases
from fruitfly_agent.lab.optimization.text_optimizer import TextProposal, SearchPreview, TEXT_OPTIMIZER_COMPONENT
from fruitfly_agent.lab.catalog import MechanismDefinition, MechanismDescriptor, MechanismContribution, builtin_catalog
from tests.support.faux_provider import FauxProvider
from tests.support.materials import _write_models, _write_cases






class OptimizationFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_auxiliary_optimizer_profile_is_in_manifest_and_shares_root_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_models(root)
            _write_cases(root)
            with (root / "models.yaml").open("a") as stream:
                stream.write("  auxiliary:\n    provider: anthropic\n    model: optimizer-model\n"
                             "    api_key_env: TEST_API_KEY\n    context_window: 4000\n    max_output_tokens: 512\n")
            main, auxiliary = FauxProvider(), FauxProvider()
            for text in ("wrong", "wrong", "A", "B"):
                main.respond_text(text)
            for text in ('["new guidance"]', '["new guidance"]'):
                auxiliary.respond_text(text)
            registry = Mock()
            registry.create.side_effect = lambda spec, _env: auxiliary if spec.model == "optimizer-model" else main
            factory = RunApplicationFactory(cwd=root, environment={"FRUITFLY_MODEL_PROFILE": "local"}, provider_registry=registry)
            factory.configuration.set_mechanism("opro", enabled=True)
            factory.configuration.set_parameter("opro", "optimizer_profile", "auxiliary")
            factory.configuration.save()
            factory.reload_configuration()
            app = AgentApplication(factory)
            await app.start()
            try:
                self.assertIn("optimizer-model", [spec["model"] for spec in app.runtime_manifest["models"].values()])
                created = await app.optimize("improve")
                self.assertEqual(len(created), 1)
                evidence = dict(created[0].evidence)
                self.assertEqual(evidence["Model attempts"], "6")
                self.assertEqual(len(main.calls), 4)
                self.assertEqual(len(auxiliary.calls), 2)
                self.assertEqual(auxiliary.calls[0]["max_tokens"], 512)
            finally:
                await app.close()

    async def test_preview_validates_and_displays_one_algorithm_snapshot(self):
        class Optimizer:
            async def search(self, prompt, direction, *, parent_manifest, task=None):
                return ()
            def cancel(self):
                return False
        optimizer = Optimizer()
        optimizer.preview = Mock(side_effect=(
            SearchPreview('custom', 'Custom', 'Offline', target_id='base_prompt'),
            SearchPreview('custom', 'Custom', 'Offline', target_id='missing-target'),
        ))
        definition = MechanismDefinition(
            MechanismDescriptor('custom', 'Custom', 'Snapshot preview',
                contributions=(MechanismContribution('optimization', 'context'),),
                default_enabled=True, exclusive_group='text-optimizer'),
            lambda state, context, params: state.with_component(TEXT_OPTIMIZER_COMPONENT, optimizer),
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_models(root)
            registry = Mock()
            registry.create.side_effect = lambda *_: FauxProvider()
            app = AgentApplication(RunApplicationFactory(cwd=root, environment={},
                catalog=builtin_catalog().extended((definition,)), provider_registry=registry))
            await app.start()
            try:
                preview = app.optimization_preview()
                self.assertEqual(preview.target, 'base_prompt')
                optimizer.preview.assert_called_once_with()
                with self.assertRaisesRegex(ValueError, 'missing-target.*not enabled'):
                    app.optimization_preview()
            finally:
                await app.close()

    async def test_injected_optimizer_uses_existing_host_without_algorithm_branches(self):
        class CustomOptimizer:
            def preview(self, *, task=None):
                return SearchPreview("custom-search", "Custom search", "Offline; no model calls")

            async def search(self, prompt, direction, *, parent_manifest, task=None):
                return (TextProposal(prompt + "\nNew guidance", "custom-search", "custom-cases", 0.0, 1.0, 1),)

            def cancel(self):
                return False

        definition = MechanismDefinition(
            MechanismDescriptor(
                "custom-search", "Custom search", "Injected optimizer",
                contributions=(MechanismContribution("optimization", "context"),),
                default_enabled=True, exclusive_group="text-optimizer",
            ),
            lambda state, context, parameters: state.with_component(TEXT_OPTIMIZER_COMPONENT, CustomOptimizer()),
            implementation_id="custom-v1",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_models(root)
            registry = Mock()
            registry.create.side_effect = lambda *_: FauxProvider()
            factory = RunApplicationFactory(
                cwd=root, environment={}, provider_registry=registry,
                catalog=builtin_catalog().extended((definition,)),
            )
            factory.configuration.save()
            factory.reload_configuration()
            app = AgentApplication(factory)
            await app.start()
            try:
                self.assertEqual("custom-search", app.optimization_preview().algorithm)
                created = await app.optimize("Improve guidance")
                self.assertEqual("custom-search", created[0].algorithm)
                app.candidate_action(created[0].candidate_id, "adopt")
                await app.rebuild()
                self.assertEqual(created[0].artifact_id, app.runtime_manifest["base_prompt"]["reference"])
            finally:
                await app.close()

    async def test_selected_opro_search_review_and_next_session_adoption(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_models(root)
            _write_cases(root)
            registry = Mock()
            registry.create.side_effect = lambda *_: FauxProvider()
            factory = RunApplicationFactory(cwd=root, environment={}, provider_registry=registry)
            factory.configuration.set_mechanism("opro", enabled=True)
            factory.configuration.save()
            factory.reload_configuration()
            app = AgentApplication(factory)
            await app.start()
            try:
                original = app.runtime_manifest["base_prompt"]["reference"]
                self.assertEqual(dict(app.optimization_preview().details)["Training cases"], "1")
                self.assertEqual(app.candidate_notice(), ())
                with patch("fruitfly_agent.lab.optimization.opro.OproOptimizer.search",
                           new=AsyncMock(side_effect=RuntimeError("search failed"))):
                    with self.assertRaisesRegex(RuntimeError, "search failed"):
                        await app.optimize("be concise")
                self.assertEqual(app.candidates(), ())
                provider = factory._current_runtime_config.provider
                seed = factory._current_targets["base_prompt"].snapshot().text
                proposals = json.dumps([seed + "\nAnswer concisely.", seed + "\nGive exact answers."])
                for text in ("wrong", "wrong", proposals, "A", "B", "wrong", "wrong", proposals):
                    provider.respond_text(text)
                created = await app.optimize("Prefer concise exact answers")
                self.assertEqual(len(created), 1)
                self.assertEqual(len(provider.calls), 8)
                self.assertTrue(all(candidate.algorithm == "opro" for candidate in created))
                self.assertEqual(app.runtime_manifest["base_prompt"]["reference"], original)
                self.assertEqual(len(app.candidate_notice()), 1)
                app.acknowledge_candidate_notice(app.candidate_notice())
                self.assertEqual(app.candidate_notice(), ())
                record, diff = app.candidate_detail(created[0].candidate_id)
                self.assertIn("Answer concisely.", diff)
                self.assertEqual(record.status, "proposed")
                app.candidate_action(record.candidate_id, "review")
                adopted = app.candidate_action(record.candidate_id, "adopt")
                self.assertEqual(adopted.status, "selected_for_next_session")
                self.assertEqual(app.runtime_manifest["base_prompt"]["reference"], original)
                saved = load_harness_config(root / ".fruitfly" / "config.yaml")
                self.assertEqual(saved.select().prompt, adopted.artifact_id)
                await app.rebuild()
                self.assertEqual(app.runtime_manifest["base_prompt"]["reference"], adopted.artifact_id)
                self.assertEqual(
                    factory.candidate_store.read(adopted.candidate_id).status,
                    "adopted",
                )
                with self.assertRaisesRegex(ValueError, "no longer adoptable"):
                    app.candidate_action(created[0].candidate_id, "adopt")
            finally:
                await app.close()
            restarted = AgentApplication(RunApplicationFactory(
                cwd=root, environment={}, provider_registry=registry
            ))
            await restarted.start()
            try:
                self.assertEqual(
                    restarted.runtime_manifest["base_prompt"]["reference"],
                    adopted.artifact_id,
                )
                self.assertEqual(restarted.candidate_notice(), ())
                self.assertEqual(len(restarted.candidates()), 1)
            finally:
                await restarted.close()

    async def test_disabled_optimizer_never_searches_or_notifies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_models(root)
            _write_cases(root)
            registry = Mock()
            registry.create.side_effect = lambda *_: FauxProvider()
            factory = RunApplicationFactory(
                cwd=root, environment={}, provider_registry=registry
            )
            app = AgentApplication(factory)
            await app.start()
            try:
                with self.assertRaisesRegex(RuntimeError, "not enabled"):
                    await app.optimize("improve")
                self.assertEqual(factory._current_runtime_config.provider.calls, [])
                self.assertEqual(app.candidate_notice(), ())
            finally:
                await app.close()

    async def test_cancelling_search_does_not_publish_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_models(root)
            _write_cases(root)
            registry = Mock()
            registry.create.side_effect = lambda *_: FauxProvider()
            factory = RunApplicationFactory(cwd=root, environment={}, provider_registry=registry)
            factory.configuration.set_mechanism("opro", enabled=True)
            factory.configuration.save()
            factory.reload_configuration()
            app = AgentApplication(factory)
            await app.start()
            try:
                started = asyncio.Event()
                cleaned = asyncio.Event()
                async def blocked():
                    started.set()
                    try:
                        await asyncio.Event().wait()
                        yield
                    finally:
                        cleaned.set()
                provider = factory._current_runtime_config.provider
                provider.script.append(lambda *args, **kwargs: AssistantMessageEventStream(blocked()))
                task = asyncio.create_task(app.optimize("test cancellation"))
                await asyncio.wait_for(started.wait(), 1)
                self.assertTrue(app.cancel())
                with self.assertRaises(asyncio.CancelledError):
                    await task
                self.assertTrue(cleaned.is_set())
                self.assertEqual(app.candidates(), ())
            finally:
                await app.close()

    def test_cases_require_disjoint_bounded_explicit_examples(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_cases(root)
            suite = load_task_cases(root, ".fruitfly/optimization/cases.json")
            self.assertEqual(len(suite.validation), 1)
            path = root / ".fruitfly" / "optimization" / "cases.json"
            path.write_text(json.dumps({
                "train": [{"input": "same", "expected": "A"}],
                "validation": [{"input": "same", "expected": "B"}],
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "overlap"):
                load_task_cases(root, ".fruitfly/optimization/cases.json")
            with self.assertRaisesRegex(ValueError, "inside the workspace"):
                load_task_cases(root, "../outside.json")
