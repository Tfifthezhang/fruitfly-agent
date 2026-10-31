"""Shared receipts preserve missing usage and validate legacy evidence identities."""
import json
from pathlib import Path
import tempfile
import unittest
from fruitfly_agent.improvement.evidence.reporting import token_usage, build_report
from fruitfly_agent.improvement.contracts.versions import content_hash as content_id


class ReportingTests(unittest.TestCase):
    def test_usage_counts_actual_attempts_and_does_not_double_add_cache(self):
        rows = [{'kind': 'request', 'id': str(i)} for i in range(4)]
        receipt = {'kind': 'response', 'attempt_id': '0', 'usage':
                   {'input_tokens': 100, 'output_tokens': 20, 'cache_read_tokens': 80}}
        rows += [receipt, receipt, {'kind': 'response', 'attempt_id': '1', 'usage': None},
                 {'kind': 'response', 'attempt_id': '2', 'usage': {'input_tokens': 0}},
                 {'kind': 'response', 'attempt_id': 'orphan', 'usage': {'input_tokens': 999}}]
        usage = token_usage(rows, 4)
        self.assertEqual((120, 80, 1, 3), (usage.total_tokens, usage.cache_read_tokens,
                                         usage.reported_calls, usage.missing_calls))

    def test_objective_direction_and_partial_evaluations(self):
        rows = [{'kind': 'evaluation', 'candidate_id': 'new', 'partition': 'train',
                 'score': .8, 'observation_ids': ['one']}]
        report = build_report(rows, baseline_id='old', candidate_id='new', train_count=2,
                              validation_count=1, seed_score=2, candidate_score=1, direction='min')
        self.assertEqual('improved', report.conclusion)
        self.assertIsNone(report.candidate_train_score)
        self.assertEqual(1, report.candidate_train_completed)
        tied = build_report([], baseline_id='old', candidate_id='new', train_count=0,
                            validation_count=0, seed_score=1, candidate_score=1)
        self.assertEqual('tied', tied.conclusion)

    def test_removed_report_allowances_are_rejected(self):
        from fruitfly_agent.improvement.evidence.reporting import SearchReport
        for name in ('model_limit','trial_limit','uncertain_model_allowance'):
            with self.subTest(name=name),self.assertRaises(TypeError):SearchReport(**{name:1})
