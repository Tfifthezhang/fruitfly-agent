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
    def setUp(self) -> None:
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.model_path = self.root / "models.yaml"
        _write_catalog(self.model_path, {"offline": "offline-model"})
        self.registry = Mock()
        self.registry.create.side_effect = lambda *_: FauxProvider()

    def assemble(self, profile, session, *, catalog, **kwargs):
        return build_runtime(
            profile, session=session, catalog=catalog, cwd=self.root,
            provider_registry=self.registry, environment=kwargs.pop("environment", {}),
            config_path=kwargs.pop("config_path", self.root / "config.yaml"), **kwargs,
        )

    def test_permission_identity_and_standard_authorizer_are_required_for_recovery(self):
        from fruitfly_agent.lab.catalog import PermissionPolicy
        from fruitfly_agent.lab.environment.guarded import GuardedEnv
        catalog = builtin_catalog()
        profile = HarnessProfile("default", str(self.model_path), "offline", catalog.default_selections())
        with Session(self.root / "permissions.jsonl") as session:
            original = self.assemble(profile, session, catalog=catalog)
            self.assertIsNotNone(original.config.tool_authorizer)
            self.assertIsInstance(original.config.env, GuardedEnv)
            self.assertEqual("confirm", original.manifest.permissions["outside_workspace"])
            record_session_manifest(session, original)
            changed = self.assemble(profile, session, catalog=catalog,
                permission_policy=PermissionPolicy(self.root, read_roots=(self.root.parent,)))
            with self.assertRaisesRegex(ValueError, "differs"):
                check_session_manifest(session, changed, resume=True)
            identical = self.assemble(profile, session, catalog=catalog)
            check_session_manifest(session, identical, resume=True)
            self.assertEqual(0, identical.components['authorization'].status()['grants'])
            self.assertFalse(identical.config.env.write_file(str(session.path), 'corrupt').is_ok)

    def test_effective_transport_defaults_and_changes_bind_recovery_identity(self):
        from tests.support.provider_streams import adapter

        catalog = builtin_catalog()
        profile = HarnessProfile("default", str(self.model_path), "offline", ())
        for kind in ("openai", "anthropic"):
            with self.subTest(kind=kind), Session(self.root / f"{kind}.jsonl") as session:
                default, _ = adapter(kind, [])
                explicit, _ = adapter(kind, [], total_timeout=900)
                changed, _ = adapter(kind, [], total_timeout=901)
                self.registry.create.side_effect = None
                self.registry.create.return_value = default
                original = self.assemble(profile, session, catalog=catalog)
                self.assertEqual(900.0, original.manifest.models["main"]["transport"]["total_timeout"])
                record_session_manifest(session, original)
                self.registry.create.return_value = explicit
                equivalent = self.assemble(profile, session, catalog=catalog)
                self.assertEqual(original.manifest.digest, equivalent.manifest.digest)
                check_session_manifest(session, equivalent, resume=True)
                self.registry.create.return_value = changed
                incompatible = self.assemble(profile, session, catalog=catalog)
                with self.assertRaisesRegex(ValueError, "differs"):
                    check_session_manifest(session, incompatible, resume=True)
                self.registry.create.return_value = FauxProvider()
                missing = self.assemble(profile, session, catalog=catalog)
                with self.assertRaisesRegex(ValueError, "differs"):
                    check_session_manifest(session, missing, resume=True)

    def test_algorithm_version_and_effective_defaults_bind_session_identity(self):
        from dataclasses import asdict, replace
        from fruitfly_agent.lab.catalog import LabCatalog
        from fruitfly_agent.lab.context_manager.reduction import SummarizingCompactorConfig

        root = self.root
        model_path = self.model_path
        catalog = builtin_catalog()
        profile = HarnessProfile("default", str(model_path), "offline", catalog.default_selections())
        with Session(root / "session.jsonl") as session:
            runtime = self.assemble(profile, session, catalog=catalog)
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
            changed = self.assemble(profile, session, catalog=changed_catalog)
            self.assertNotEqual(runtime.manifest.digest, changed.manifest.digest)
            with self.assertRaisesRegex(ValueError, "differs"):
                check_session_manifest(session, changed, resume=True)

    def test_base_prompt_artifact_changes_runtime_identity_and_verified_default_recovers(self) -> None:
        root = self.root
        model_path = self.model_path
        catalog = builtin_catalog()
        store = DataArtifactStore(root / ".fruitfly" / "artifacts")
        ref = store.put_text("A distinct base prompt")
        baseline = HarnessProfile("default", str(model_path), "offline", tuple(s for s in catalog.default_selections() if s.mechanism_id != "compaction"))
        candidate = HarnessProfile("default", str(model_path), "offline", baseline.mechanisms, ref.artifact_id)
        with Session(root / ".fruitfly" / "sessions" / "first.jsonl") as session:
            original = self.assemble(baseline, session, catalog=catalog, artifact_store=store)
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
            changed = self.assemble(candidate, session, catalog=catalog, artifact_store=store)
            self.assertEqual(changed.config.system_prompt, "A distinct base prompt")
            self.assertEqual(changed.manifest.base_prompt["content_hash"], ref.artifact_id)
            self.assertNotEqual(changed.manifest.digest, original.manifest.digest)
            record_session_manifest(session, changed)
            check_session_manifest(session, changed, resume=True)
            (store.root / ref.artifact_id[7:]).write_text("tampered", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hash check"):
                self.assemble(candidate, session, catalog=catalog, artifact_store=store)

    def test_sessions_without_prompt_identity_require_verified_provenance(self) -> None:
        root = self.root
        model_path = self.model_path
        catalog = builtin_catalog()
        profile = HarnessProfile(
            "default", str(model_path), "offline",
            tuple(s for s in catalog.default_selections() if s.mechanism_id != "compaction"),
        )
        for schema_version in (3, 4):
            with self.subTest(schema_version=schema_version):
                path = root / f"schema-{schema_version}.jsonl"
                with Session(path) as session:
                    runtime = self.assemble(profile, session, catalog=catalog)
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
                        "fruitfly_agent.run.recovery._LEGACY_DEFAULT_PROMPT_HASH",
                        DEFAULT_PROMPT.content_hash,
                    ):
                        check_session_manifest(
                            session, runtime, resume=True, allow_legacy_default_prompt=True
                        )
                        with self.assertRaisesRegex(ValueError, "cannot be verified"):
                            check_session_manifest(session, runtime, resume=True)
                    self.assertEqual(contents, path.read_bytes())

    def test_data_artifact_store_is_content_addressed_and_detects_tampering(self) -> None:
        store = DataArtifactStore(self.root / "artifacts")
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
        root = self.root
        model_path = self.model_path
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
            runtime = self.assemble(
                profile, session, catalog=catalog, artifact_store=store,
                artifact_bindings={'skill-catalog.guidance': ref.artifact_id},
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
        root = self.root
        model_path = self.model_path
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
                self.assemble(
                    profile, session, catalog=catalog, artifact_store=store,
                    artifact_bindings={'skill-catalog.guidance': ref.artifact_id},
                )

    def test_guidance_artifact_requires_the_mechanism_to_be_enabled(self) -> None:
        root = self.root
        model_path = self.model_path
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
                self.assemble(
                    profile, session, catalog=catalog, artifact_store=store,
                    artifact_bindings={'skill-catalog.guidance': ref.artifact_id},
                )

    def test_baseline_components_are_not_reported_as_lab_mechanisms(self) -> None:
        root = self.root
        model_path = self.model_path
        catalog = builtin_catalog()
        profile = HarnessProfile(
            "default",
            model_catalog=str(model_path),
            model_profile="offline",
            mechanisms=catalog.default_selections(),
        )
        with Session(root / "baseline.jsonl") as session:
            runtime = self.assemble(profile, session, catalog=catalog)
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
        root = self.root
        model_path = self.model_path
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
                return self.assemble(profile, session, config_path=path, catalog=catalog)

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
        root = self.root
        model_path = self.model_path
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
            runtime = self.assemble(
                profile, session, config_path=root / 'fruitfly.yaml', catalog=catalog,
                environment={'TEST_API_KEY': 'placeholder'},
            )

        self.assertEqual(
            [tool.name for tool in runtime.config.tools],
            ["read", "edit", "write"],
        )
        self.assertNotIn("bash-tool", runtime.mechanism_ids)

    def test_information_sources_do_not_add_provider_or_memory_tool(self) -> None:
        root = self.root
        model_path = self.model_path
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
            registry = self.registry
            registry.reset_mock()
            with Session(root / f"{enabled}.jsonl") as session:
                runtime = self.assemble(
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
        root = self.root
        model_path = self.model_path
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
        registry = self.registry
        session_path = root / "rlm.jsonl"

        with Session(session_path) as session:
            runtime = self.assemble(
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

class RuntimePermissionWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_external_tools_confirm_and_restore_does_not_restore_grants(self):
        from fruitfly_agent.interactive import AgentApplication
        from fruitfly_agent.run import RunApplicationFactory
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            workspace = root / 'workspace'
            workspace.mkdir()
            _write_catalog(workspace / 'models.yaml', {'offline': 'offline-model'})
            provider = FauxProvider()
            registry = Mock()
            registry.create.return_value = provider
            factory = RunApplicationFactory(cwd=workspace,
                environment={'TEST_API_KEY': 'offline-placeholder'}, provider_registry=registry)
            factory.configuration.set_mechanism('compaction', enabled=False)
            factory.configuration.save()
            factory.reload_configuration()
            app = AgentApplication(factory)
            self.addAsyncCleanup(app.close)
            prompts = []
            async def approve(prompt):
                prompts.append(prompt)
                return 'session'
            app.set_authorization_handler(approve)
            path = workspace / '.fruitfly' / 'sessions' / 'permissions.jsonl'
            await app.start(session_path=path)
            target = root / 'outside.txt'
            provider.respond_tool_call('write', {'path': str(target), 'content': 'first'})
            provider.respond_text('written')
            result = await app.submit('write external file')
            self.assertFalse(result.is_error)
            self.assertEqual('first', target.read_text())
            self.assertEqual(1, len(prompts))
            self.assertEqual(1, app.status.permission_grants)
            provider.respond_tool_call('read', {'path': str(target)})
            provider.respond_text('read')
            await app.submit('read approved directory')
            self.assertEqual(1, len(prompts))
            await app.close()
            await app.start(resume=True, session_path=path)
            self.assertEqual(0, app.status.permission_grants)
            provider.respond_tool_call('write', {'path': str(target), 'content': 'second'})
            provider.respond_text('written again')
            await app.submit('write after restore')
            self.assertEqual(2, len(prompts))
            self.assertEqual('second', target.read_text())
            app.clear_authorizations()
            self.assertEqual(0, app.status.permission_grants)
            await app.close()
            with Session(path) as durable:
                decisions = [e.payload for e in durable.read_all() if e.payload.get('kind') == 'authorization']
                self.assertEqual(3, len(decisions))
                self.assertTrue(all(e['allowed'] for e in decisions))
                self.assertTrue(all('arguments' not in e and 'command' not in e for e in decisions))
