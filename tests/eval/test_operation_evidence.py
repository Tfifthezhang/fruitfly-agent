"""Eval consumes runtime facts without inferring outcomes from missing evidence."""
from pathlib import Path
import tempfile
import unittest

from fruitfly_agent.core.observation import ObservationContext, bind_observation, operation
from fruitfly_agent.core.session import Session
from fruitfly_agent.core.session.observations import session_observer
from fruitfly_eval.harbor.budget import execution_budget
from fruitfly_eval.harbor.diagnostics import attach_evidence, trial_diagnostics
from fruitfly_eval.harbor.tasks import coverage_report


class OperationEvidenceTests(unittest.TestCase):
    def test_allowance_capacity_includes_attempts_concurrency_longest_and_unknowns(self):
        tasks = [{'configuration': {'agent': {'timeout_sec': value}}} for value in (100, 500, None)]
        result = execution_budget(tasks, 2, 4, 300)
        self.assertEqual(1200, result['agent_allowance_seconds'])
        self.assertEqual(300, result['agent_allowance_per_worker_seconds'])
        self.assertEqual(500, result['minimum_capacity_for_declared_allowances_seconds'])
        self.assertTrue(result['shorter_than_agent_allowances'])
        self.assertEqual(1, result['tasks_without_agent_allowance'])
        self.assertEqual([100, 500, None], [task['configuration']['agent']['timeout_sec'] for task in tasks])

    def test_coverage_keeps_missing_and_unexpected_attempts_distinct(self):
        report = coverage_report([{'id': 'repo/a', 'name': 'a'}, {'id': 'repo/b', 'name': 'b'}],
            [{'task_id': 'a'}, {'task_id': 'a'}, {'task_id': 'extra'}], 2)
        self.assertEqual({'repo/b': 2}, report['missing_results'])
        self.assertEqual({'extra': 1}, report['unexpected_results'])

    def test_collection_failure_and_torn_last_write_do_not_change_official_reward(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path = root / 'agent/session.jsonl'
            with Session(path) as session:
                with bind_observation(ObservationContext(sink=session_observer(session), run_id='run')):
                    with operation('request.prepare'):
                        pass
            with path.open('a') as output:
                output.write('{"partial":')
            trial = {}
            attach_evidence(trial, root)
            facts = trial_diagnostics(trial, reward=0)
            self.assertEqual('collected', facts['agent_operations']['collection_state'])
            self.assertIn('request.prepare', facts['agent_operations']['stages'])
            self.assertEqual(0, facts['official_reward'])
            self.assertEqual('completed', facts['state'])
            path.write_text('not JSON\n')
            attach_evidence(trial, root)
            self.assertEqual('collection_failed', trial['_agent_operations']['collection_state'])

    def test_startup_sidecar_is_collected_when_no_agent_session_was_written(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'agent/session.jsonl.operations/startup.jsonl'
            with Session(path) as session:
                with bind_observation(ObservationContext(sink=session_observer(session), run_id='startup')):
                    with operation('application.start'):
                        pass
            trial = {}
            attach_evidence(trial, root)
            facts = trial_diagnostics(trial, reward=None)
            self.assertEqual('collected', facts['agent_operations']['collection_state'])
            self.assertIn('application.start', facts['agent_operations']['stages'])
            self.assertEqual('error', facts['state'])
