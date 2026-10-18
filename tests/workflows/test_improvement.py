"""Offline end-to-end improver selection, inbox, and next-session adoption."""

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
from fruitfly_agent.lab.improvement.tasks.cases import load_task_cases
from fruitfly_agent.lab.improvement.api import TextProposal, SearchPreview, TEXT_IMPROVER_COMPONENT
from fruitfly_agent.lab.catalog import MechanismDefinition, MechanismDescriptor, MechanismContribution, builtin_catalog
from tests.support.faux_provider import FauxProvider
from tests.support.materials import _write_models, _write_cases






class ImprovementFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_regular_search_freezes_state_before_work_and_rechecks_before_adoption(self):
        from tests.support.improvers import offline_factory
        for phase in ('preview', 'adoption'):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                factory = offline_factory(root)
                app = AgentApplication(factory)
                await app.start()
                try:
                    preview = app.improvement_preview(direction='Improve')
                    self.assertIn('Parent H/S/I', dict(preview.details))
                    if phase == 'adoption':
                        candidate = (await app.improve('Improve', preview_token=preview.preview_token))[0]
                        self.assertEqual(candidate.role, 'H')
                        self.assertIn('Version candidate', dict(candidate.evidence))
                    memory = root / '.fruitfly/memory'
                    memory.mkdir(parents=True, exist_ok=True)
                    (memory / 'MEMORY.md').write_text('Changed initial learning state')
                    with self.assertRaisesRegex(ValueError, 'H[/]?[SI/]'):
                        if phase == 'preview':
                            await app.improve('Improve', preview_token=preview.preview_token)
                        else:
                            await app.adopt_candidate(candidate.candidate_id)
                    self.assertEqual(factory._current_improver.calls, 0 if phase == 'preview' else 1)
                finally:
                    await app.close()

    async def test_auxiliary_improver_profile_is_in_manifest_and_shares_root_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_models(root)
            _write_cases(root)
            with (root / "models.yaml").open("a") as stream:
                stream.write("  auxiliary:\n    provider: anthropic\n    model: improver-model\n"
                             "    api_key_env: TEST_API_KEY\n    context_window: 4000\n    max_output_tokens: 512\n")
            main, auxiliary = FauxProvider(), FauxProvider()
            for text in ("wrong", "wrong", "A", "B"):
                main.respond_text(text)
            for text in ('["new guidance"]', '["new guidance"]'):
                auxiliary.respond_text(text)
            registry = Mock()
            registry.create.side_effect = lambda spec, _env: auxiliary if spec.model == "improver-model" else main
            factory = RunApplicationFactory(cwd=root, environment={"FRUITFLY_MODEL_PROFILE": "local"}, provider_registry=registry)
            factory.configuration.set_mechanism("opro", enabled=True)
            factory.configuration.set_parameter("opro", "improver_profile", "auxiliary")
            factory.configuration.save()
            factory.reload_configuration()
            app = AgentApplication(factory)
            await app.start()
            try:
                self.assertIn("improver-model", [spec["model"] for spec in app.runtime_manifest["models"].values()])
                created = await app.improve("improve")
                self.assertEqual(len(created), 1)
                evidence = dict(created[0].evidence)
                self.assertEqual(evidence["Model attempts"], "6")
                self.assertEqual(len(main.calls), 4)
                self.assertEqual(len(auxiliary.calls), 2)
                self.assertEqual(auxiliary.calls[0]["max_tokens"], 512)
            finally:
                await app.close()

    async def test_preview_validates_and_displays_one_algorithm_snapshot(self):
        class Improver:
            async def search(self, prompt, direction, *, parent_manifest, task=None):
                return ()
            def cancel(self):
                return False
        improver = Improver()
        improver.preview = Mock(side_effect=(
            SearchPreview('custom', 'Custom', 'Offline', target_id='base_prompt'),
            SearchPreview('custom', 'Custom', 'Offline', target_id='missing-target'),
        ))
        definition = MechanismDefinition(
            MechanismDescriptor('custom', 'Custom', 'Snapshot preview',
                contributions=(MechanismContribution('improvement', 'context'),),
                default_enabled=True, exclusive_group='text-improver'),
            lambda state, context, params: state.with_component(TEXT_IMPROVER_COMPONENT, improver),

            implementation_path='tests/workflows/test_improvement.py',
            documentation_path='tests/workflows/README.md',
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
                preview = app.improvement_preview()
                self.assertEqual(preview.target, 'base_prompt')
                improver.preview.assert_called_once_with()
                with self.assertRaisesRegex(ValueError, 'missing-target.*not enabled'):
                    app.improvement_preview()
            finally:
                await app.close()

    async def test_injected_improver_uses_existing_host_without_algorithm_branches(self):
        class CustomImprover:
            def preview(self, *, task=None):
                return SearchPreview("custom-search", "Custom search", "Offline; no model calls")

            async def search(self, prompt, direction, *, parent_manifest, task=None):
                return (TextProposal(prompt + "\nNew guidance", "custom-search", "custom-cases", 0.0, 1.0, 1),)

            def cancel(self):
                return False

        definition = MechanismDefinition(
            MechanismDescriptor(
                "custom-search", "Custom search", "Injected improver",
                contributions=(MechanismContribution("improvement", "context"),),
                default_enabled=True, exclusive_group="text-improver",
            ),
            lambda state, context, parameters: state.with_component(TEXT_IMPROVER_COMPONENT, CustomImprover()),
            implementation_id="custom-v1",

            implementation_path='tests/workflows/test_improvement.py',
            documentation_path='tests/workflows/README.md',
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
                self.assertEqual("custom-search", app.improvement_preview().algorithm)
                created = await app.improve("Improve guidance")
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
                self.assertEqual(dict(app.improvement_preview().details)["Training cases"], "1")
                self.assertEqual(app.candidate_notice(), ())
                with patch("fruitfly_agent.lab.improvement.methods.opro.OproImprover.search",
                           new=AsyncMock(side_effect=RuntimeError("search failed"))):
                    with self.assertRaisesRegex(RuntimeError, "search failed"):
                        await app.improve("be concise")
                self.assertEqual(app.candidates(), ())
                provider = factory._current_runtime_config.provider
                seed = factory._current_targets["base_prompt"].snapshot().text
                proposals = json.dumps([seed + "\nAnswer concisely.", seed + "\nGive exact answers."])
                for text in ("wrong", "wrong", proposals, "A", "B", "wrong", "wrong", proposals):
                    provider.respond_text(text)
                created = await app.improve("Prefer concise exact answers")
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

    async def test_unconfigured_methods_are_discovered_without_starting_search(self):
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
                self.assertIsNone(factory._current_improver.host)
                self.assertTrue({'opro', 'tree-search'} <= {m.method_id for m in
                    app.improvement_methods('H', 'base_prompt') if m.available})
                self.assertTrue(any(m.available for m in app.improvement_methods('I', 'tree-search.exploration-policy')))
                preview = app.improvement_preview(direction='improve', method_id='opro', target_id='base_prompt')
                self.assertEqual(preview.algorithm, 'opro')
                self.assertIsNone(factory._current_improver.host)
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
                task = asyncio.create_task(app.improve("test cancellation"))
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
            suite = load_task_cases(root, ".fruitfly/improvement/cases.json")
            self.assertEqual(len(suite.validation), 1)
            path = root / ".fruitfly" / "improvement" / "cases.json"
            path.write_text(json.dumps({
                "train": [{"input": "same", "expected": "A"}],
                "validation": [{"input": "same", "expected": "B"}],
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "overlap"):
                load_task_cases(root, ".fruitfly/improvement/cases.json")
            with self.assertRaisesRegex(ValueError, "inside the workspace"):
                load_task_cases(root, "../outside.json")
