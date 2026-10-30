"""Recovery behavior and failure contracts."""
from __future__ import annotations
from dataclasses import replace
import tempfile
import unittest
from fruitfly_agent.core.session import Session
from fruitfly_agent.lab.catalog import builtin_catalog
from fruitfly_agent.run.configuration import HarnessProfile
from fruitfly_agent.run.application import check_session_manifest, record_session_manifest
from tests.support.faux_provider import FauxProvider

from tests.support.assembly import AssemblyWorkspace


class RuntimeAssemblyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = AssemblyWorkspace(self.enterContext(tempfile.TemporaryDirectory()))

    def test_changed_permissions_allow_recovery_with_current_authorizer(self):
        from fruitfly_agent.lab.catalog import PermissionPolicy
        from fruitfly_agent.lab.environment.guarded import GuardedEnv
        catalog = builtin_catalog()
        profile = HarnessProfile("default", str(self.workspace.model_path), "offline", catalog.default_selections())
        with Session(self.workspace.root / "permissions.jsonl") as session:
            original = self.workspace.assemble(profile, session, catalog=catalog)
            self.assertIsNotNone(original.config.tool_authorizer)
            self.assertIsInstance(original.config.env, GuardedEnv)
            self.assertEqual("confirm", original.manifest.permissions["outside_workspace"])
            record_session_manifest(session, original)
            changed = self.workspace.assemble(profile, session, catalog=catalog,
                permission_policy=PermissionPolicy(self.workspace.root, read_roots=(self.workspace.root.parent,)))
            check_session_manifest(session, changed, resume=True)
            identical = self.workspace.assemble(profile, session, catalog=catalog)
            check_session_manifest(session, identical, resume=True)
            self.assertEqual(0, identical.components['authorization'].status()['grants'])
            self.assertFalse(identical.config.env.write_file(str(session.path), 'corrupt').is_ok)

    def test_transport_identity_is_recorded_but_changes_allow_recovery(self):
        from tests.support.provider_streams import adapter

        catalog = builtin_catalog()
        profile = HarnessProfile("default", str(self.workspace.model_path), "offline", ())
        for kind in ("openai", "anthropic"):
            with self.subTest(kind=kind), Session(self.workspace.root / f"{kind}.jsonl") as session:
                default, _ = adapter(kind, [])
                explicit, _ = adapter(kind, [], total_timeout=900)
                changed, _ = adapter(kind, [], total_timeout=901)
                self.workspace.registry.create.side_effect = None
                self.workspace.registry.create.return_value = default
                original = self.workspace.assemble(profile, session, catalog=catalog)
                self.assertEqual(900.0, original.manifest.models["main"]["transport"]["total_timeout"])
                record_session_manifest(session, original)
                self.workspace.registry.create.return_value = explicit
                equivalent = self.workspace.assemble(profile, session, catalog=catalog)
                self.assertEqual(original.manifest.digest, equivalent.manifest.digest)
                check_session_manifest(session, equivalent, resume=True)
                self.workspace.registry.create.return_value = changed
                incompatible = self.workspace.assemble(profile, session, catalog=catalog)
                check_session_manifest(session, incompatible, resume=True)
                self.workspace.registry.create.return_value = FauxProvider()
                missing = self.workspace.assemble(profile, session, catalog=catalog)
                check_session_manifest(session, missing, resume=True)

    def test_algorithm_identity_is_recorded_but_changes_allow_recovery(self):
        from dataclasses import asdict, replace
        from fruitfly_agent.lab.catalog import LabCatalog
        from fruitfly_agent.lab.context_manager.reduction import SummarizingCompactorConfig

        root = self.workspace.root
        model_path = self.workspace.model_path
        catalog = builtin_catalog()
        profile = HarnessProfile("default", str(model_path), "offline", catalog.default_selections())
        with Session(root / "session.jsonl") as session:
            runtime = self.workspace.assemble(profile, session, catalog=catalog)
            component = next(c for c in runtime.manifest.components if c["id"] == "compaction")
            self.assertEqual("summarizing-v3", component["implementation_id"])
            self.assertEqual(asdict(SummarizingCompactorConfig()), component["parameters"])
            record_session_manifest(session, runtime)
            changed_catalog = LabCatalog(tuple(
                replace(d, implementation_id="test-summary-implementation") if d.descriptor.mechanism_id == "compaction" else d
                for d in catalog.definitions()
            ))
            changed = self.workspace.assemble(profile, session, catalog=changed_catalog)
            self.assertNotEqual(runtime.manifest.digest, changed.manifest.digest)
            check_session_manifest(session, changed, resume=True)

    def test_legacy_manifests_are_validated_without_reconstructing_old_defaults(self):
        from fruitfly_agent.run.runtime.manifest import digest_manifest
        catalog = builtin_catalog()
        profile = HarnessProfile("default", str(self.workspace.model_path), "offline", ())
        for version in (3, 4, 5, 6):
            with self.subTest(version=version), Session(self.workspace.root / f"legacy-{version}.jsonl") as session:
                runtime = self.workspace.assemble(profile, session, catalog=catalog)
                stored = runtime.manifest.to_dict()
                stored.pop("digest")
                stored.pop("permissions")
                stored.pop("harness")
                if version < 6:
                    stored.pop("execution")
                stored["schema_version"] = version
                if version < 5:
                    stored.pop("base_prompt")
                stored["digest"] = digest_manifest(stored)
                session.append("meta", {"kind": "runtimeManifest", "manifest": stored}, sync=True)
                before = session.path.read_bytes()
                check_session_manifest(session, runtime, resume=True)
                self.assertEqual(before, session.path.read_bytes())
                record_session_manifest(session, runtime)
                self.assertEqual(stored, session.read_all()[0].payload["manifest"])
                self.assertEqual(runtime.manifest.to_dict(), session.read_all()[-1].payload["manifest"])
                record_session_manifest(session, runtime)
                self.assertEqual(2, len(session.read_all()))
