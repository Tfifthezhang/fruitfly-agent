from __future__ import annotations

from datetime import UTC, datetime
import unittest

from eval.contracts import EvaluationRequest
from eval.planning import create_plan
from tests.support.evaluation import request_payload


class PlanningTests(unittest.TestCase):
    def test_current_setup_has_one_frozen_condition(self) -> None:
        plan = create_plan(
            EvaluationRequest.from_dict(request_payload()),
            now=datetime(2026, 1, 2, tzinfo=UTC),
        )
        self.assertTrue(plan.evaluation_id.startswith("20260102T000000Z-"))
        self.assertEqual([item["condition_id"] for item in plan.conditions], ["current"])
        self.assertTrue(plan.network["provider"])
        self.assertFalse(plan.reproducibility["secret_values_persisted"])
        self.assertEqual(
            plan.benchmark["smoke_task"], "swe-bench/psf__requests-1142"
        )
        self.assertEqual(
            plan.reproducibility["task_order"], "fixed_declared_smoke_task"
        )

    def test_mechanism_comparison_removes_only_target(self) -> None:
        payload = request_payload(mode="mechanism_comparison")
        payload["runtime"]["manifest"]["components"] = [
            {
                "id": "compaction",
                "contributions": [{"layer": "online", "family": "context", "context_phase": "reduction"}],
                "activation": "runtime",
                "parameters": {},
            }
        ]
        plan = create_plan(EvaluationRequest.from_dict(payload))
        self.assertEqual(
            [item["condition_id"] for item in plan.conditions],
            ["baseline", "candidate"],
        )
        self.assertEqual(
            plan.conditions[0]["mechanism_overrides"],
            {"compaction": {"enabled": False}},
        )
        self.assertEqual(plan.conditions[1]["mechanism_overrides"], {})
        self.assertEqual(
            plan.conditions[0]["base_runtime_manifest_digest"], "sha256:test"
        )

    def test_inactive_comparison_mechanism_is_rejected(self) -> None:
        request = EvaluationRequest.from_dict(
            request_payload(mode="mechanism_comparison")
        )
        with self.assertRaisesRegex(ValueError, "is not active"):
            create_plan(request)

    def test_comparison_rejects_target_required_by_another_active_mechanism(self) -> None:
        payload = request_payload(mode="mechanism_comparison")
        payload["runtime"]["manifest"]["components"] = [
            {
                "id": "compaction",
                "contributions": [{"layer": "online", "family": "context", "context_phase": "reduction"}],
                "requires": [],
                "parameters": {},
            },
            {
                "id": "dependent",
                "contributions": [{"layer": "optimization", "family": "workflow", "context_phase": None}],
                "requires": ["compaction"],
                "parameters": {},
            },
        ]
        request = EvaluationRequest.from_dict(payload)

        with self.assertRaisesRegex(ValueError, "active mechanisms require it: dependent"):
            create_plan(request)


if __name__ == "__main__":
    unittest.main()
