from __future__ import annotations


from dataclasses import replace



import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fruitfly_agent.core.data_model import UserMessage
from fruitfly_agent.core.context import ContextFrame
from fruitfly_agent.core.session import Session

from fruitfly_agent.lab.catalog import (
    MechanismSelection,
    builtin_catalog,
)
from fruitfly_agent.run.configuration import HarnessProfile
from fruitfly_agent.run import DataArtifactStore, build_runtime


from fruitfly_agent.run.application import discover_resumable_sessions
from fruitfly_agent.run.application import check_session_manifest, record_session_manifest
from fruitfly_agent.lab.base_prompt import DEFAULT_PROMPT
from tests.support.faux_provider import FauxProvider
from tests.support.run import _write_catalog


class RuntimeAssemblyTest(unittest.TestCase):
    def test_algorithm_version_and_effective_defaults_bind_session_identity(self):
        from dataclasses import asdict, replace
        from fruitfly_agent.lab.catalog import LabCatalog
        from fruitfly_agent.lab.context_manager.reduction import SummarizingCompactorConfig

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model_path = root / "models.yaml"
            _write_catalog(model_path, {"offline": "offline-model"})
            catalog = builtin_catalog()
            profile = HarnessProfile("default", str(model_path), "offline", catalog.default_selections())
            registry = Mock()
            registry.create.side_effect = lambda *_: FauxProvider()
            with Session(root / "session.jsonl") as session:
                runtime = build_runtime(profile, config_path=root / "config.yaml", catalog=catalog,
                                        environment={}, session=session, cwd=root, provider_registry=registry)
                component = next(c for c in runtime.manifest.components if c["id"] == "compaction")
                self.assertEqual("summarizing-v2", component["implementation_id"])
                self.assertEqual(asdict(SummarizingCompactorConfig()), component["parameters"])
                with self.assertRaisesRegex(ValueError, "algorithm identity"):
                    runtime.manifest.legacy_dict(3)
                record_session_manifest(session, runtime)
                changed_catalog = LabCatalog(tuple(
                    replace(d, implementation_id="summarizing-v3") if d.descriptor.mechanism_id == "compaction" else d
                    for d in catalog.definitions()
                ))
                changed = build_runtime(profile, config_path=root / "config.yaml", catalog=changed_catalog,
                                        environment={}, session=session, cwd=root, provider_registry=registry)
                self.assertNotEqual(runtime.manifest.digest, changed.manifest.digest)
                with self.assertRaisesRegex(ValueError, "differs"):
                    check_session_manifest(session, changed, resume=True)

    def test_base_prompt_artifact_changes_runtime_identity_and_verified_default_recovers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model_path = root / "models.yaml"
            _write_catalog(model_path, {"offline": "offline-model"})
            catalog = builtin_catalog()
            store = DataArtifactStore(root / ".fruitfly" / "artifacts")
            ref = store.put_text("A distinct base prompt")
            registry = Mock()
            registry.create.side_effect = lambda *_: FauxProvider()
            baseline = HarnessProfile("default", str(model_path), "offline", tuple(s for s in catalog.default_selections() if s.mechanism_id != "compaction"))
            candidate = HarnessProfile("default", str(model_path), "offline", baseline.mechanisms, ref.artifact_id)
            with Session(root / ".fruitfly" / "sessions" / "first.jsonl") as session:
                original = build_runtime(baseline, config_path=root / "config.yaml", catalog=catalog, environment={}, session=session, cwd=root, provider_registry=registry, artifact_store=store)
                self.assertEqual(original.config.system_prompt, DEFAULT_PROMPT.text)
                self.assertEqual(original.manifest.base_prompt["content_hash"], DEFAULT_PROMPT.content_hash)
                record_session_manifest(session, original)
                session.append("message", {"message": UserMessage(content="saved").to_dict()})
                check_session_manifest(session, original, resume=True)
            discovered = discover_resumable_sessions(
                root, manifest_digests={original.manifest.digest}
            )
            self.assertEqual(discovered[0].prompt_label, DEFAULT_PROMPT.label)
            self.assertEqual(discovered[0].prompt_hash, DEFAULT_PROMPT.content_hash)
            with Session(root / "second.jsonl") as session:
                changed = build_runtime(candidate, config_path=root / "config.yaml", catalog=catalog, environment={}, session=session, cwd=root, provider_registry=registry, artifact_store=store)
                self.assertEqual(changed.config.system_prompt, "A distinct base prompt")
                self.assertEqual(changed.manifest.base_prompt["content_hash"], ref.artifact_id)
                self.assertNotEqual(changed.manifest.digest, original.manifest.digest)
                record_session_manifest(session, changed)
                check_session_manifest(session, changed, resume=True)
                (store.root / ref.artifact_id[7:]).write_text("tampered", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "hash check"):
                    build_runtime(candidate, config_path=root / "config.yaml", catalog=catalog, environment={}, session=session, cwd=root, provider_registry=registry, artifact_store=store)

    def test_sessions_without_prompt_identity_require_verified_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model_path = root / "models.yaml"
            _write_catalog(model_path, {"offline": "offline-model"})
            catalog = builtin_catalog()
            profile = HarnessProfile(
                "default", str(model_path), "offline",
                tuple(s for s in catalog.default_selections() if s.mechanism_id != "compaction"),
            )
            registry = Mock()
            registry.create.side_effect = lambda *_: FauxProvider()
            for schema_version in (3, 4):
                with self.subTest(schema_version=schema_version):
                    path = root / f"schema-{schema_version}.jsonl"
                    with Session(path) as session:
                        runtime = build_runtime(
                            profile, config_path=root / "config.yaml", catalog=catalog,
                            environment={}, session=session, cwd=root, provider_registry=registry,
                        )
                        session.append("meta", {
                            "kind": "runtimeManifest",
                            "manifest": runtime.manifest.legacy_dict(schema_version),
                        }, sync=True)
                        contents = path.read_bytes()
                        for allow in (False, True):
                            with self.subTest(allow=allow):
                                with self.assertRaisesRegex(ValueError, "prompt identity cannot be verified"):
                                    check_session_manifest(
                                        session, runtime, resume=True, allow_legacy_default_prompt=allow
                                    )
                        with patch(
                            "fruitfly_agent.run.application._LEGACY_DEFAULT_PROMPT_HASH",
                            DEFAULT_PROMPT.content_hash,
                        ):
                            check_session_manifest(
                                session, runtime, resume=True, allow_legacy_default_prompt=True
                            )
                            with self.assertRaisesRegex(ValueError, "cannot be verified"):
                                check_session_manifest(session, runtime, resume=True)
                        self.assertEqual(contents, path.read_bytes())

    def test_data_artifact_store_is_content_addressed_and_detects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = DataArtifactStore(Path(tmp) / "artifacts")
            first = store.put_text("candidate guidance")
            repeated = store.put_text("candidate guidance")

            self.assertEqual(first, repeated)
            self.assertEqual("candidate guidance", store.read_text(first.artifact_id))
            (store.root / first.artifact_id.removeprefix("sha256:")).write_text(
                "changed", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "hash check"):
                store.read_text(first.artifact_id)

    def test_skill_guidance_artifact_is_bound_to_runtime_manifest_and_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model_path = root / "models.yaml"
            _write_catalog(model_path, {"offline": "offline-model"})
            store = DataArtifactStore(root / ".fruitfly" / "artifacts")
            ref = store.put_text("Candidate guidance version A")
            catalog = builtin_catalog()
            profile = HarnessProfile(
                "default",
                model_catalog=str(model_path),
                model_profile="offline",
                mechanisms=catalog.default_selections(),
            )
            registry = Mock()
            registry.create.side_effect = lambda *_: FauxProvider()
            with Session(root / "candidate.jsonl") as session:
                runtime = build_runtime(
                    profile,
                    config_path=root / "config.yaml",
                    catalog=catalog,
                    environment={},
                    session=session,
                    cwd=root,
                    provider_registry=registry,
                    artifact_store=store,
                    artifact_bindings={"skill-catalog.guidance": ref.artifact_id},
                )

            self.assertEqual(runtime.manifest.schema_version, 5)
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
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model_path = root / "models.yaml"
            _write_catalog(model_path, {"offline": "offline-model"})
            store = DataArtifactStore(root / ".fruitfly" / "artifacts")
            ref = store.put_text("x" * 16_000)
            catalog = builtin_catalog()
            profile = HarnessProfile(
                "default",
                model_catalog=str(model_path),
                model_profile="offline",
                mechanisms=catalog.default_selections(),
            )
            registry = Mock()
            registry.create.side_effect = lambda *_: FauxProvider()
            with Session(root / "oversized.jsonl") as session:
                with self.assertRaisesRegex(ValueError, "exceeds.*max_chars"):
                    build_runtime(
                        profile,
                        config_path=root / "config.yaml",
                        catalog=catalog,
                        environment={},
                        session=session,
                        cwd=root,
                        provider_registry=registry,
                        artifact_store=store,
                        artifact_bindings={
                            "skill-catalog.guidance": ref.artifact_id,
                        },
                    )

    def test_guidance_artifact_requires_the_mechanism_to_be_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model_path = root / "models.yaml"
            _write_catalog(model_path, {"offline": "offline-model"})
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
            registry = Mock()
            registry.create.side_effect = lambda *_: FauxProvider()
            with Session(root / "disabled.jsonl") as session:
                with self.assertRaisesRegex(ValueError, "not consumed"):
                    build_runtime(
                        profile,
                        config_path=root / "config.yaml",
                        catalog=catalog,
                        environment={},
                        session=session,
                        cwd=root,
                        provider_registry=registry,
                        artifact_store=store,
                        artifact_bindings={
                            "skill-catalog.guidance": ref.artifact_id,
                        },
                    )

    def test_baseline_components_are_not_reported_as_lab_mechanisms(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model_path = root / "models.yaml"
            _write_catalog(model_path, {"offline": "offline-model"})
            catalog = builtin_catalog()
            profile = HarnessProfile(
                "default",
                model_catalog=str(model_path),
                model_profile="offline",
                mechanisms=catalog.default_selections(),
            )
            registry = Mock()
            registry.create.side_effect = lambda *_: FauxProvider()
            with Session(root / "baseline.jsonl") as session:
                runtime = build_runtime(
                    profile,
                    config_path=root / "config.yaml",
                    catalog=catalog,
                    environment={},
                    session=session,
                    cwd=root,
                    provider_registry=registry,
                )
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
            ("skill-catalog", "information-context", "compaction"),
        )
        self.assertEqual(runtime.manifest.schema_version, 5)
        self.assertEqual(runtime.manifest.data_artifacts, ())

    def test_runtime_manifest_ignores_unused_model_catalog_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model_path = root / "models.yaml"
            _write_catalog(model_path, {"main": "model-a", "unused": "model-b"})
            catalog = builtin_catalog()
            profile = HarnessProfile(
                "default",
                model_catalog=str(model_path),
                model_profile="main",
                mechanisms=catalog.default_selections(),
            )

            def assemble(path: Path, session_path: Path):
                registry = Mock()
                registry.create.side_effect = lambda *_: FauxProvider()
                with Session(session_path) as session:
                    return build_runtime(
                        profile,
                        config_path=path,
                        catalog=catalog,
                        environment={},
                        session=session,
                        cwd=root,
                        provider_registry=registry,
                    )

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

    def test_builtin_tools_are_individually_selectable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model_path = root / "models.yaml"
            _write_catalog(model_path, {"offline": "offline-model"})
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
            registry = Mock()
            registry.create.side_effect = lambda *_: FauxProvider()

            with Session(root / "tools.jsonl") as session:
                runtime = build_runtime(
                    profile,
                    config_path=root / "fruitfly.yaml",
                    catalog=catalog,
                    environment={"TEST_API_KEY": "placeholder"},
                    session=session,
                    cwd=root,
                    provider_registry=registry,
                )

        self.assertEqual(
            [tool.name for tool in runtime.config.tools],
            ["read", "edit", "write"],
        )
        self.assertNotIn("bash-tool", runtime.mechanism_ids)

    def test_information_sources_do_not_add_provider_or_memory_tool(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model_path = root / "models.yaml"
            _write_catalog(model_path, {"offline": "offline-model"})
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
                registry = Mock()
                registry.create.side_effect = lambda *_: FauxProvider()
                with Session(root / f"{enabled}.jsonl") as session:
                    runtime = build_runtime(
                        profile,
                        config_path=root / "fruitfly.yaml",
                        catalog=catalog,
                        environment={"TEST_API_KEY": "placeholder"},
                        session=session,
                        cwd=root,
                        provider_registry=registry,
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
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model_path = root / "models.yaml"
            _write_catalog(model_path, {"offline": "offline-model"})
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
            registry = Mock()
            registry.create.side_effect = lambda *_: FauxProvider()
            session_path = root / "rlm.jsonl"

            with Session(session_path) as session:
                runtime = build_runtime(
                    profile,
                    config_path=root / "fruitfly.yaml",
                    catalog=catalog,
                    environment={"TEST_API_KEY": "placeholder"},
                    session=session,
                    cwd=root,
                    provider_registry=registry,
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
