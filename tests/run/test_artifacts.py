"""Artifacts behavior and failure contracts."""
from __future__ import annotations
import tempfile
import unittest
from fruitfly_agent.run import DataArtifactStore

from tests.support.assembly import AssemblyWorkspace


class RuntimeAssemblyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = AssemblyWorkspace(self.enterContext(tempfile.TemporaryDirectory()))

    def test_data_artifact_store_is_content_addressed_and_detects_tampering(self) -> None:
        store = DataArtifactStore(self.workspace.root / "artifacts")
        first = store.put_text("candidate guidance")
        repeated = store.put_text("candidate guidance")

        self.assertEqual(first, repeated)
        self.assertEqual("candidate guidance", store.read_text(first.artifact_id))
        (store.root / first.artifact_id.removeprefix("sha256:")).write_text(
            "changed", encoding="utf-8"
        )
        with self.assertRaisesRegex(ValueError, "hash check"):
            store.read_text(first.artifact_id)
