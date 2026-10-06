"""Public task-package isolation, edits, conflicts and snapshot guarantees."""
import fcntl
import json
from pathlib import Path
import tempfile
import unittest

from fruitfly_agent.lab.optimization.task_packs import (
    TaskPackCatalog, TaskPackRegistration, TaskSnapshotStore, validate_pack, LEGACY_PACK_ID,
    package_documents, load_pack,
)
from tests.support.task_packs import package, install, validate_material








class TaskPackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.path = install(self.root)
        self.catalog = TaskPackCatalog(self.root)

    def test_projection_excludes_holdout_and_metadata(self):
        frozen = self.catalog.freeze("project", "base_prompt")
        self.assertNotIn("SECRET", repr(frozen))
        self.assertNotIn("METADATA", repr(frozen))
        self.assertEqual("A", frozen.train[0].expected)
        self.assertEqual("SECRET_ANSWER", self.catalog.holdout("project")[0].expected)
        old_digest = frozen.digest
        payload = package()
        payload["holdout"][0]["expected"] = "CHANGED"
        install(self.root, payload)
        changed = self.catalog.freeze("project", "base_prompt")
        self.assertEqual(old_digest, changed.digest)
        self.assertNotEqual(frozen.source_hash, changed.source_hash)

    def test_schema_rejects_leakage_and_bad_types(self):
        mutations = [lambda p: p["validation"][0].update(input=" say A "),
            lambda p: p["validation"][0].update(id="train-1"),
            lambda p: p.update(compatible_targets=[{}]),
            lambda p: p.update(schema_version=True),
            lambda p: p.update(objective=dict(policy_id="shell", direction="max")),
            lambda p: p["train"][0].update(expected=""),
            lambda p: p["train"][0].update(input="a" * 4001),
            lambda p: p["train"][0].update(extra="unknown")]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                payload = package()
                mutate(payload)
                with self.assertRaises(ValueError):
                    validate_material(payload)
        payload = package()
        payload["train"][0]["group_id"] = "same-scenario"
        payload["validation"][0]["group_id"] = "same-scenario"
        with self.assertRaisesRegex(ValueError, "group_id"):
            validate_material(payload)

    def test_append_idempotency_explicit_replace_and_cas(self):
        original = load_pack(self.root, self.path).material
        identity = self.catalog.source_hash("project")
        self.catalog.save_training("project", "say C", "C", expected_hash=identity)
        updated = load_pack(self.root, self.path).material
        self.assertEqual(original["validation"], updated["validation"])
        self.assertEqual(original["holdout"], updated["holdout"])
        with self.assertRaisesRegex(ValueError, "changed"):
            self.catalog.save_training("project", "say D", "D", expected_hash=identity)
        identity = self.catalog.source_hash("project")
        before = self.path.read_bytes()
        self.catalog.save_training("project", "say C", "C", expected_hash=identity)
        self.assertEqual(before, self.path.read_bytes())
        with self.assertRaisesRegex(ValueError, "conflicting"):
            self.catalog.save_training("project", "say C", "corrected", expected_hash=identity)
        self.catalog.save_training("project", "say C", "corrected", expected_hash=identity, replace=True)
        self.assertEqual("corrected", self.catalog.freeze("project", "base_prompt").train[-1].expected)

    def test_validation_and_holdout_cannot_be_changed_by_correction(self):
        for question in ("say B", "UNSEEN_INPUT"):
            before = self.path.read_bytes()
            with self.assertRaisesRegex(ValueError, "validation/holdout"):
                self.catalog.save_training("project", question, "changed", expected_hash=self.catalog.source_hash("project"), replace=True)
            self.assertEqual(before, self.path.read_bytes())

    def test_new_package_can_save_but_not_search_without_validation(self):
        pack_id = self.catalog.save_training("", "a self-contained question", "human answer", name="Corrections")
        self.assertEqual(1, next(p for p in self.catalog.summaries() if p.pack_id == pack_id).train_count)
        with self.assertRaisesRegex(ValueError, "independent validation"):
            self.catalog.freeze(pack_id, "base_prompt")

    def test_readonly_source_requires_explicit_copy(self):
        source = self.root / "examples/pack.json"
        source.parent.mkdir()
        self.path.parent.rename(source.parent / "package")
        source = source.parent / "package/pack.json"
        catalog = TaskPackCatalog(self.root, (TaskPackRegistration(source),))
        identity = catalog.source_hash("project")
        original = source.read_bytes()
        with self.assertRaisesRegex(ValueError, "read-only"):
            catalog.save_training("project", "new", "answer", expected_hash=identity)
        copied = catalog.save_training("project", "new", "answer", expected_hash=identity, copy=True)
        self.assertNotEqual("project", copied)
        self.assertEqual(original, source.read_bytes())
        self.assertEqual(2, len(catalog.freeze(copied, "base_prompt").train))

    def test_legacy_source_can_be_copied_without_editing_original(self):
        path = self.root / "old.json"
        path.write_text(json.dumps({k: [{a: c[a] for a in ("input", "expected")} for c in package()[k]] for k in ("train", "validation")}))
        catalog = TaskPackCatalog(self.root, legacy_path="old.json")
        before = path.read_bytes()
        pack_id = catalog.save_training(LEGACY_PACK_ID, "new", "answer", expected_hash=catalog.source_hash(LEGACY_PACK_ID), copy=True)
        self.assertEqual(before, path.read_bytes())
        self.assertEqual(2, len(catalog.freeze(pack_id, "base_prompt").train))

    def test_duplicate_package_ids_and_incompatible_target_are_errors(self):
        other = self.path.parent.parent / "duplicate/pack.json"
        other.parent.mkdir()
        other.write_bytes(self.path.read_bytes())
        for name in ("cases.json", "holdout.json"):
            (other.parent/name).write_bytes((self.path.parent/name).read_bytes())
        self.assertTrue(all(p.error for p in self.catalog.summaries()))
        with self.assertRaises(ValueError):
            self.catalog.freeze("project", "base_prompt")
        other.unlink()
        with self.assertRaisesRegex(ValueError, "target"):
            self.catalog.freeze("project", "unsupported")

    def test_paths_symlinks_size_and_duplicate_fields_rejected(self):
        with self.assertRaisesRegex(ValueError, "workspace"):
            TaskPackCatalog(self.root, (TaskPackRegistration(Path("../outside")),)).summaries()
        self.path.unlink()
        self.path.symlink_to(self.root / "elsewhere")
        self.assertTrue(self.catalog.summaries()[0].error)
        self.path.unlink()
        self.path.write_text('{"id":"a","id":"b"}')
        self.assertIn("duplicate JSON", self.catalog.summaries()[0].error)
        self.path.write_bytes(b" " * 100001)
        self.assertIn("100 KB", self.catalog.summaries()[0].error)

    def test_writer_lock_and_failed_write_preserve_original(self):
        before = self.path.read_bytes()
        lock = self.catalog.root / ".write.lock"
        with lock.open("a") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError, "another process"):
                self.catalog.save_training("project", "new", "answer", expected_hash=self.catalog.source_hash("project"))
        with self.assertRaises(ValueError):
            self.catalog.save_training("project", "new", "answer", reason="x" * 1001, expected_hash=self.catalog.source_hash("project"))
        self.assertEqual(before, self.path.read_bytes())

    def test_content_addressed_snapshots_are_reused_and_verified(self):
        store = TaskSnapshotStore(self.root)
        path, identity = store.freeze({"tasks": ["one"]})
        self.assertEqual((path, identity), store.freeze({"tasks": ["one"]}))
        path.write_text("corrupted")
        with self.assertRaisesRegex(ValueError, "corrupted"):
            store.verify(path, identity)
        with self.assertRaisesRegex(ValueError, "corrupted"):
            store.freeze({"tasks": ["one"]})

    def test_optional_default_legacy_source_is_absent_from_package_choices(self):
        for path in (".fruitfly/optimization/cases.json", str(self.root / ".fruitfly/optimization/cases.json")):
            catalog = TaskPackCatalog(self.root, legacy_path=path)
            with self.subTest(path=path):
                self.assertEqual(["project"], [s.pack_id for s in catalog.summaries("base_prompt")])
                self.assertEqual(1, len(catalog.freeze("project", "base_prompt").train))
        # Explicit custom paths and broken existing files must retain actionable errors.
        custom = TaskPackCatalog(self.root, legacy_path="my-missing-cases.json")
        self.assertTrue(next(s for s in custom.summaries() if s.pack_id == LEGACY_PACK_ID).error)
        source = self.root / ".fruitfly/optimization/cases.json"
        source.write_text("broken json")
        default = TaskPackCatalog(self.root, legacy_path=str(source))
        self.assertTrue(next(s for s in default.summaries() if s.pack_id == LEGACY_PACK_ID).error)
        source.write_text(json.dumps({"train":[{"input":"old train","expected":"A"}],"validation":[{"input":"old validation","expected":"B"}]}))
        legacy = next(s for s in default.summaries() if s.pack_id == LEGACY_PACK_ID)
        self.assertEqual("", legacy.error)
        self.assertEqual(1, legacy.train_count)
