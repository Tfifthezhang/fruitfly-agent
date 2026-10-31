"""Assembly behavior and failure contracts."""
from __future__ import annotations
from dataclasses import replace
import tempfile
import unittest
from pathlib import Path
from fruitfly_agent.core.data_model import UserMessage
from fruitfly_agent.core.context import ContextFrame
from fruitfly_agent.core.session import Session
from fruitfly_agent.lab.catalog import (
    MechanismSelection,
    builtin_catalog,
)
from fruitfly_agent.run.configuration import HarnessProfile
from fruitfly_agent.run import DataArtifactStore
from fruitfly_agent.run.adapters.runtime import describe_runtime
from fruitfly_agent.run.application import discover_resumable_sessions
from fruitfly_agent.run.application import check_session_manifest, record_session_manifest
from fruitfly_agent.lab.base_prompt import DEFAULT_PROMPT
from tests.support.run import _write_catalog

from tests.support.assembly import AssemblyWorkspace


class RuntimeAssemblyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = AssemblyWorkspace(self.enterContext(tempfile.TemporaryDirectory()))

    def test_base_prompt_artifact_changes_runtime_identity_and_verified_default_recovers(self) -> None:
        root = self.workspace.root
        model_path = self.workspace.model_path
        catalog = builtin_catalog()
        store = DataArtifactStore(root / ".fruitfly" / "artifacts")
        ref = store.put_text("A distinct base prompt")
        baseline = HarnessProfile("default", str(model_path), "offline", tuple(s for s in catalog.default_selections() if s.mechanism_id != "working-memory-reduction"))
        candidate = HarnessProfile("default", str(model_path), "offline", baseline.mechanisms, ref.artifact_id)
        with Session(root / ".fruitfly" / "sessions" / "first.jsonl") as session:
            original = self.workspace.assemble(baseline, session, catalog=catalog, artifact_store=store)
            self.assertEqual(original.config.system_prompt, DEFAULT_PROMPT.text)
            self.assertEqual(original.manifest.base_prompt["content_hash"], DEFAULT_PROMPT.content_hash)
            record_session_manifest(session, original)
            session.append("message", {"message": UserMessage(content="saved").to_dict()})
            check_session_manifest(session, original, resume=True)
        discovered = discover_resumable_sessions(
            root
        )
        self.assertEqual(discovered[0].prompt_label, DEFAULT_PROMPT.label)
        self.assertEqual(discovered[0].prompt_hash, DEFAULT_PROMPT.content_hash)
        with Session(root / "second.jsonl") as session:
            changed = self.workspace.assemble(candidate, session, catalog=catalog, artifact_store=store)
            self.assertEqual(changed.config.system_prompt, "A distinct base prompt")
            self.assertEqual(changed.manifest.base_prompt["content_hash"], ref.artifact_id)
            self.assertNotEqual(changed.manifest.digest, original.manifest.digest)
            record_session_manifest(session, changed)
            check_session_manifest(session, changed, resume=True)
            (store.root / ref.artifact_id[7:]).write_text("tampered", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hash check"):
                self.workspace.assemble(candidate, session, catalog=catalog, artifact_store=store)

    def test_skill_guidance_artifact_is_bound_to_runtime_manifest_and_context(self) -> None:
        root = self.workspace.root
        model_path = self.workspace.model_path
        store = DataArtifactStore(root / ".fruitfly" / "artifacts")
        ref = store.put_text("Candidate guidance version A")
        catalog = builtin_catalog()
        profile = HarnessProfile(
            "default",
            model_catalog=str(model_path),
            model_profile="offline",
            mechanisms=catalog.default_selections(),
        )
        with Session(root / "candidate.jsonl") as session:
            runtime = self.workspace.assemble(
                profile, session, catalog=catalog, artifact_store=store,
                artifact_bindings={'skill-catalog.guidance': ref.artifact_id},
            )

        self.assertEqual(runtime.manifest.schema_version, 7)
        self.assertEqual(
            runtime.manifest.data_artifacts[0]["id"], ref.artifact_id
        )
        stage = next(
            item for item in runtime.context_pipeline.stages
            if item.stage_id == "skill-catalog"
        )
        transformed = stage.mechanism.transform(
            ContextFrame("base", (), (), "offline-model", 32)
        )

        self.assertIn("Candidate guidance version A", transformed.frame.system_prompt)

    def test_oversized_guidance_artifact_fails_runtime_assembly(self) -> None:
        root = self.workspace.root
        model_path = self.workspace.model_path
        store = DataArtifactStore(root / ".fruitfly" / "artifacts")
        ref = store.put_text("x" * 16_000)
        catalog = builtin_catalog()
        profile = HarnessProfile(
            "default",
            model_catalog=str(model_path),
            model_profile="offline",
            mechanisms=catalog.default_selections(),
        )
        with Session(root / "oversized.jsonl") as session:
            with self.assertRaisesRegex(ValueError, "exceeds.*max_chars"):
                self.workspace.assemble(
                    profile, session, catalog=catalog, artifact_store=store,
                    artifact_bindings={'skill-catalog.guidance': ref.artifact_id},
                )

    def test_guidance_artifact_requires_the_mechanism_to_be_enabled(self) -> None:
        root = self.workspace.root
        model_path = self.workspace.model_path
        store = DataArtifactStore(root / ".fruitfly" / "artifacts")
        ref = store.put_text("candidate")
        catalog = builtin_catalog()
        profile = HarnessProfile(
            "default",
            model_catalog=str(model_path),
            model_profile="offline",
            mechanisms=tuple(
                item for item in catalog.default_selections()
                if item.mechanism_id != "skill-catalog"
            ),
        )
        with Session(root / "disabled.jsonl") as session:
            with self.assertRaisesRegex(ValueError, "not consumed"):
                self.workspace.assemble(
                    profile, session, catalog=catalog, artifact_store=store,
                    artifact_bindings={'skill-catalog.guidance': ref.artifact_id},
                )

    def test_baseline_components_are_not_reported_as_lab_mechanisms(self) -> None:
        root = self.workspace.root
        model_path = self.workspace.model_path
        catalog = builtin_catalog()
        profile = HarnessProfile(
            "default",
            model_catalog=str(model_path),
            model_profile="offline",
            mechanisms=catalog.default_selections(),
        )
        with Session(root / "baseline.jsonl") as session:
            runtime = self.workspace.assemble(profile, session, catalog=catalog)
        self.assertFalse((root / ".fruitfly" / "artifacts").exists())

        self.assertTrue(
            {
                "local-env",
                "read-tool",
                "bash-tool",
                "edit-tool",
                "write-tool",
            }.issubset(runtime.component_ids)
        )
        self.assertEqual(
            runtime.mechanism_ids,
            ("skill-catalog", "information-context", "working-memory-reduction", "component-improvement"),
        )
        self.assertEqual(runtime.manifest.schema_version, 7)
        self.assertEqual(runtime.manifest.data_artifacts, ())

    def test_runtime_manifest_ignores_unused_model_catalog_entries(self) -> None:
        root = self.workspace.root
        model_path = self.workspace.model_path
        _write_catalog(model_path, {"main": "model-a", "unused": "model-b"})
        catalog = builtin_catalog()
        profile = HarnessProfile(
            "default",
            model_catalog=str(model_path),
            model_profile="main",
            mechanisms=catalog.default_selections(),
        )

        def assemble(path: Path, session_path: Path):
            with Session(session_path) as session:
                return self.workspace.assemble(profile, session, config_path=path, catalog=catalog)

        first = assemble(root / "config.yaml", root / "first.jsonl")
        _write_catalog(
            model_path,
            {
                "main": "model-a",
                "unused": "changed-unused-model",
                "new-unused": "model-c",
            },
        )
        second = assemble(root / "config.yaml", root / "second.jsonl")

        self.assertEqual(first.manifest.digest, second.manifest.digest)
        self.assertEqual(set(first.manifest.models), {"main", "auxiliary-1"})

    def test_runtime_overview_includes_capabilities_and_preserves_experimental_ids(self) -> None:
        catalog = builtin_catalog()
        profile = HarnessProfile('default', str(self.workspace.model_path), 'offline', catalog.default_selections())
        with Session(self.workspace.root / 'overview.jsonl') as session:
            runtime = self.workspace.assemble(profile, session, catalog=catalog)
        experiment_ids, details, tool_categories = describe_runtime(runtime, catalog)
        views = {item.mechanism_id: item for item in details}
        self.assertNotIn('local-env', experiment_ids)
        self.assertNotIn('read-tool', experiment_ids)
        self.assertEqual('environment', views['local-env'].category)
        self.assertEqual('tools', views['read-tool'].category)
        self.assertEqual(('read',), views['read-tool'].tool_names)
        self.assertEqual('reduction', views['working-memory-reduction'].display_section)
        self.assertNotIn('information-context', views)
        self.assertNotIn('web-search-tool', views)
        self.assertEqual('tools', tool_categories['read'])
        self.assertEqual([], runtime.config.provider.calls)

    def test_runtime_overview_respects_registration_category_metadata(self) -> None:
        from fruitfly_agent.lab.catalog import LabCatalog

        catalog = builtin_catalog()
        catalog = LabCatalog(tuple(
            replace(definition, configuration_category='learning')
            if definition.descriptor.mechanism_id == 'skill-catalog' else definition
            for definition in catalog.definitions()
        ))
        profile = HarnessProfile('default', str(self.workspace.model_path), 'offline', catalog.default_selections())
        with Session(self.workspace.root / 'overview-category.jsonl') as session:
            runtime = self.workspace.assemble(profile, session, catalog=catalog)
        _, details, _ = describe_runtime(runtime, catalog)
        view = next(item for item in details if item.mechanism_id == 'skill-catalog')
        self.assertEqual('learning', view.category)

    def test_builtin_tools_are_individually_selectable(self) -> None:
        root = self.workspace.root
        model_path = self.workspace.model_path
        catalog = builtin_catalog()
        mechanisms = tuple(
            MechanismSelection(
                item.mechanism_id,
                enabled=item.mechanism_id != "bash-tool",
                parameters=item.parameters,
            )
            for item in catalog.default_selections()
        )
        profile = HarnessProfile(
            "default",
            model_catalog=str(model_path),
            model_profile="offline",
            mechanisms=mechanisms,
        )

        with Session(root / "tools.jsonl") as session:
            runtime = self.workspace.assemble(
                profile, session, config_path=root / 'fruitfly.yaml', catalog=catalog,
                environment={'TEST_API_KEY': 'placeholder'},
            )

        self.assertEqual(
            [tool.name for tool in runtime.config.tools],
            ["read", "edit", "write", "context_read", "context_search"],
        )
        self.assertNotIn("bash-tool", runtime.mechanism_ids)

    def test_information_sources_do_not_add_provider_or_memory_tool(self) -> None:
        root = self.workspace.root
        model_path = self.workspace.model_path
        catalog = builtin_catalog()
        base = HarnessProfile(
            "default",
            model_catalog=str(model_path),
            model_profile="offline",
            mechanisms=catalog.default_selections(),
        )
        for enabled in (False, True):
            mechanisms = base.mechanisms
            if enabled:
                mechanisms = (*mechanisms, MechanismSelection("knowledge-files"))
            profile = HarnessProfile(
                "default",
                model_catalog=str(model_path),
                model_profile="offline",
                mechanisms=mechanisms,
            )
            registry = self.workspace.registry
            registry.reset_mock()
            with Session(root / f"{enabled}.jsonl") as session:
                runtime = self.workspace.assemble(
                    profile, session, config_path=root / 'fruitfly.yaml', catalog=catalog,
                    environment={'TEST_API_KEY': 'placeholder'},
                )

            self.assertEqual(registry.create.call_count, 2)
            self.assertFalse(any(
                tool.name.startswith("memory_") for tool in runtime.config.tools
            ))
            self.assertEqual(
                "knowledge-files" in runtime.component_ids,
                enabled,
            )

    def test_rlm_runtime_uses_session_path_and_adds_auxiliary_provider(self) -> None:
        root = self.workspace.root
        model_path = self.workspace.model_path
        catalog = builtin_catalog()
        mechanisms = (
            *catalog.default_selections(),
            MechanismSelection("ipython-tool"),
            MechanismSelection("rlm-ipython"),
        )
        profile = HarnessProfile(
            "default",
            model_catalog=str(model_path),
            model_profile="offline",
            mechanisms=mechanisms,
        )
        registry = self.workspace.registry
        session_path = root / "rlm.jsonl"

        with Session(session_path) as session:
            runtime = self.workspace.assemble(
                profile, session, config_path=root / 'fruitfly.yaml', catalog=catalog,
                environment={'TEST_API_KEY': 'placeholder'},
            )
        artifact_exists = (
            session_path.with_suffix(".jsonl.artifacts")
            .joinpath("rlm")
            .is_dir()
        )

        self.assertEqual(3, registry.create.call_count)
        self.assertIn("rlm-ipython", runtime.mechanism_ids)
        self.assertIn("ipython-tool", runtime.components)
        self.assertIn("ipython", [tool.name for tool in runtime.config.tools])
        self.assertEqual(
            {"main", "auxiliary-1", "auxiliary-2"},
            set(runtime.manifest.models),
        )
        self.assertTrue(artifact_exists)
