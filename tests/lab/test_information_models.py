"""Information envelopes and narrow capability contracts."""

from __future__ import annotations

import unittest

from fruitfly_agent.lab.context_manager.augmentation.information import (
    InformationArtifact,
    InformationQuery,
    InformationReader,
    InformationRef,
)


class _Reader:
    def get(self, ref):
        return None


class InformationModelTests(unittest.TestCase):
    def test_structured_payload_has_deterministic_text(self) -> None:
        artifact = InformationArtifact(
            ref=InformationRef("docs", "one"),
            payload={"z": 1, "a": "Ｖ"},
            representation="structured",
            media_type="application/json",
        )
        self.assertEqual('{"a": "Ｖ", "z": 1}', artifact.text)

    def test_invalid_query_budget_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "top_k"):
            InformationQuery("query", top_k=0)
        with self.assertRaisesRegex(ValueError, "max_chars"):
            InformationQuery("query", max_chars=0)

    def test_confidence_and_trust_are_bounded(self) -> None:
        with self.assertRaisesRegex(ValueError, "confidence"):
            InformationArtifact(InformationRef("s", "a"), "x", confidence=1.1)
        with self.assertRaisesRegex(ValueError, "trust"):
            InformationArtifact(InformationRef("s", "a"), "x", trust=-0.1)

    def test_hand_rolled_reader_satisfies_protocol(self) -> None:
        self.assertIsInstance(_Reader(), InformationReader)


if __name__ == "__main__":
    unittest.main()
