from __future__ import annotations

import unittest

from eval.contracts import EvaluationRequest
from tests.support.evaluation import request_payload


class EvaluationRequestTests(unittest.TestCase):

    def test_comparison_requires_one_mechanism(self) -> None:
        payload = request_payload(mode="mechanism_comparison")
        payload["comparison"] = None
        with self.assertRaisesRegex(ValueError, "comparison is required"):
            EvaluationRequest.from_dict(payload)

if __name__ == "__main__":
    unittest.main()
