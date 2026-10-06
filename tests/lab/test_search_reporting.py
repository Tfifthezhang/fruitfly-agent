"""Shared receipts preserve missing usage and validate legacy evidence identities."""
import json
from pathlib import Path
import tempfile
import unittest
from fruitfly_agent.lab.optimization.reporting import token_usage, build_report, restore_search_report
from fruitfly_agent.lab.optimization.search import content_id


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

    def test_legacy_recovery_uses_frozen_cases_and_checks_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            identity = {'search_id': 'search', 'parent_manifest': 'parent', 'cases_digest': 'cases'}
            rows = [{'kind': 'problem', 'baseline_hash': 'old', 'parameters':
                     {'max_metric_calls': 4, 'max_model_calls': 8}},
                    {'kind': 'evaluation', 'candidate_id': 'old', 'partition': 'validation',
                     'score': 1., 'observation_ids': ['old-case']},
                    {'kind': 'evaluation', 'candidate_id': 'new', 'partition': 'validation',
                     'score': 1., 'observation_ids': ['new-case']},
                    {'kind': 'search-result', 'status': 'budget_exhausted',
                     'candidates': ['new'], 'usage': {'model': 3, 'trial': 4}}]
            history = '.fruitfly/optimization/searches/search.jsonl'
            snapshot = '.fruitfly/optimization/task-snapshots/task.json'
            (root / history).parent.mkdir(parents=True)
            (root / snapshot).parent.mkdir()
            encoded = '\n'.join(json.dumps({**row, **identity}) for row in rows)
            frozen = json.dumps({'target_hash': 'old', 'task': {'cases_digest': 'cases',
                                                               'train': [{}], 'validation': [{}]}})
            (root / history).write_text(encoded)
            (root / snapshot).write_text(frozen)
            args = dict(history=history, history_hash=content_id(encoded), snapshot=snapshot,
                        snapshot_hash=content_id(frozen), candidate_id='new', baseline_id='old',
                        parent_manifest='parent', cases_digest='cases')
            report = restore_search_report(root, **args)
            self.assertEqual(('tied', 'trial', 1, 3),
                             (report.conclusion, report.exhausted_kind, report.validation_count,
                              report.tokens.missing_calls))
            self.assertIsNone(report.candidate_train_score)
            with self.assertRaises(ValueError):
                restore_search_report(root, **{**args, 'candidate_id': 'unrelated'})
            (root / history).write_text(encoded + ' ')
            with self.assertRaises(ValueError):
                restore_search_report(root, **args)

            malformed = json.dumps([1, 2])
            (root / history).write_text(malformed)
            with self.assertRaises(ValueError):
                restore_search_report(root, **{**args, 'history_hash': content_id(malformed)})
