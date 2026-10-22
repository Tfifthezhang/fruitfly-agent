"""Optional measured verification; output selection alone never grants adoption."""
from __future__ import annotations

from inspect import isawaitable
from dataclasses import asdict

from ..contracts.pipeline import Measurement, SelectionDecision, canonical_json


class CaseMeasurements:
    """Answers remain inside this injected verifier and never enter TaskMaterial."""
    direction = 'max'
    def __init__(self, policy, cases):
        self.policy = policy
        self.cases = dict(cases)

    async def measure(self, task, record):
        if record.status != 'completed' or task.task_id not in self.cases:
            return None
        result = self.policy.score(record.output, self.cases[task.task_id])
        if isawaitable(result):
            result = await result
        score = result.score if hasattr(result, 'score') else result
        feedback = result.feedback if hasattr(result, 'feedback') else ''
        return Measurement(record.run_id, self.policy.policy_id, score, feedback)


class HoldoutVerification:
    """Compare unchanged original selection and holdout tasks once after editing.

    The executor is a budgeted host capability. Verification tasks and answers
    are not supplied to generators, composers or reflection.
    """
    policy_id = 'task-holdout-v1'
    def __init__(self, *, baseline, selection, holdout, execute, measurements,
                 direction='max', min_gain=0, max_case_regression=0, regression=(), artifacts=None):
        if not selection or not holdout:
            raise ValueError('persistent comparison requires selection and independent holdout')
        if {t.material_id for t in selection} & {t.material_id for t in holdout}:
            raise ValueError('verification partitions must not overlap')
        if direction not in {'max', 'min'} or min_gain < 0 or max_case_regression < 0:
            raise ValueError('invalid fixed verification policy')
        self.baseline, self.selection, self.holdout = baseline, tuple(selection), tuple(holdout)
        self.execute, self.measurements = execute, measurements
        self.direction, self.min_gain, self.max_case_regression = direction, min_gain, max_case_regression
        self.regression = tuple(regression)
        self.receipts = []
        self.artifacts, self.receipt = artifacts, None

    async def verify(self, outcome):
        utility = 1 if self.direction == 'max' else -1
        for partition, strict_gain in ((self.regression, False), (self.selection, True), (self.holdout, True)):
            gains = []
            for task in partition:
                before = await self.execute(task, self.baseline)
                after = await self.execute(task, outcome.harness)
                a = await self.measurements.measure(task, before)
                b = await self.measurements.measure(task, after)
                self.receipts.append((before, after, a, b))
                if a is None or b is None:
                    return None
                gain = utility * (b.score - a.score)
                if gain < -self.max_case_regression:
                    return None
                gains.append(gain)
            if strict_gain and sum(gains) / len(gains) <= self.min_gain:
                return None
        if self.artifacts is not None:
            self.receipt = self.artifacts.put(canonical_json({'schema_version': 1,
                'policy_id': self.policy_id, 'direction': self.direction, 'min_gain': self.min_gain,
                'max_case_regression': self.max_case_regression, 'conditions_id': outcome.plan.conditions_id,
                'before': self.baseline.snapshot_id, 'after': outcome.harness.snapshot_id,
                'receipts': [[asdict(v) if v is not None else None for v in row] for row in self.receipts]}).encode())
        return SelectionDecision(outcome.selected.run_id,
            'Passed fixed selection and independent holdout comparisons', 'verified')


__all__ = ['CaseMeasurements', 'HoldoutVerification']
