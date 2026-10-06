"""Offline base-prompt identity and artifact checks."""

import tempfile
import unittest
import hashlib
from pathlib import Path

from fruitfly_agent.lab.base_prompt import DEFAULT_PROMPT, DEFAULT_PROMPT_ID, get_builtin, builtins
from fruitfly_agent.run.artifacts import DataArtifactStore
from fruitfly_agent.run.assembly import resolve_base_prompt


class BasePromptTest(unittest.TestCase):
    def test_default_text_and_identity_are_stable(self) -> None:
        store = DataArtifactStore(Path(tempfile.gettempdir()) / "fruitfly-unused-artifacts")
        text, identity = resolve_base_prompt(DEFAULT_PROMPT_ID, store)
        self.assertEqual(text, DEFAULT_PROMPT.text)
        self.assertEqual(identity["content_hash"], DEFAULT_PROMPT.content_hash)
        self.assertEqual(DEFAULT_PROMPT_ID, "assistant-default")
        self.assertEqual(DEFAULT_PROMPT.label, "Assistant default")
        self.assertEqual(
            DEFAULT_PROMPT.content_hash,
            "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest(),
        )
        self.assertIs(get_builtin(DEFAULT_PROMPT_ID), DEFAULT_PROMPT)

    def test_default_instructions_are_only_general_assistance(self) -> None:
        self.assertEqual(
            DEFAULT_PROMPT.text,
            "You are FruitFlyAgent, a general-purpose assistant. Help the user understand, "
            "create, and solve problems. Use available tools when useful; be concise.",
        )

    def test_only_project_default_is_bundled(self) -> None:
        self.assertEqual((DEFAULT_PROMPT,), builtins())

    def test_unknown_prompt_references_are_rejected(self) -> None:
        store = DataArtifactStore(Path(tempfile.gettempdir()) / "fruitfly-unused-artifacts")
        for reference in ("unregistered-prompt", "unregistered-prompt-variant"):
            with self.subTest(reference=reference):
                with self.assertRaisesRegex(ValueError, "unknown built-in base prompt"):
                    get_builtin(reference)
                with self.assertRaises(ValueError):
                    resolve_base_prompt(reference, store)

    def test_artifact_is_verified_and_missing_or_invalid_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = DataArtifactStore(Path(tmp))
            ref = store.put_text("Candidate instructions")
            text, identity = resolve_base_prompt(ref.artifact_id, store)
            self.assertEqual(text, "Candidate instructions")
            self.assertEqual(identity["content_hash"], ref.artifact_id)
            self.assertIn(ref.artifact_id, store.list_text_ids())
            (Path(tmp) / ref.artifact_id[7:]).write_text("tampered", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hash check"):
                resolve_base_prompt(ref.artifact_id, store)
            with self.assertRaises(ValueError):
                resolve_base_prompt("unknown", store)
            with self.assertRaises(ValueError):
                resolve_base_prompt("sha256:bad", store)

    def test_artifact_symlink_is_not_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = DataArtifactStore(root / "artifacts")
            ref = store.put_text("Trusted prompt")
            path = store.root / ref.artifact_id[7:]
            path.unlink()
            outside = root / "other.txt"
            outside.write_text("Trusted prompt", encoding="utf-8")
            path.symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "symlink"):
                resolve_base_prompt(ref.artifact_id, store)
            self.assertNotIn(ref.artifact_id, store.list_text_ids())


if __name__ == "__main__":
    unittest.main()
