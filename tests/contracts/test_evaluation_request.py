"""Accepted request fields and explicit rejection of removed experiment features."""
import unittest
from eval.contracts import EvaluationRequest
from tests.support.evaluation import request_payload


class EvaluationRequestTests(unittest.TestCase):
    def test_experimental_fields_are_rejected(self):
        for field, value in (("mode", "mechanism_comparison"), ("comparison", {"mechanism_id": "compaction"}),
                             ("conditions", []), ("reproducibility", {})):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "unsupported request fields"):
                EvaluationRequest.from_dict({**request_payload(), field: value})

    def test_execution_options_are_real_positive_integers(self):
        for key in ("attempts", "concurrency", "timeout_seconds"):
            for value in (0, -1, True, 1.5):
                payload = request_payload()
                payload["execution"][key] = value
                with self.subTest(key=key, value=value), self.assertRaisesRegex(ValueError, "positive integer"):
                    EvaluationRequest.from_dict(payload)
        payload = request_payload()
        payload["execution"]["seed"] = 7
        with self.assertRaisesRegex(ValueError, "unsupported execution fields"):
            EvaluationRequest.from_dict(payload)

    def test_request_does_not_require_historical_runtime_identity(self):
        request = EvaluationRequest.from_dict(request_payload())
        self.assertEqual("test", request.runtime.profile)
        self.assertNotIn("manifest", request.to_dict()["runtime"])
