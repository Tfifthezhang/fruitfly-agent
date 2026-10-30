"""Joint selection requires common complete evidence, with explicit collection weights."""
from dataclasses import replace
import unittest
from fruitfly_agent.improvement.contracts.task_sets import TaskSetSnapshot
from fruitfly_agent.improvement.contracts.evaluation import EvaluationBatch, TrialResult, CandidateEvaluation
from fruitfly_agent.improvement.contracts.execution import ExecutionRecord
from fruitfly_agent.improvement.contracts.assessment import Measurement
from fruitfly_agent.lab.improvement.task_sets import MultiTaskSettings
from fruitfly_agent.improvement.contracts.versions import content_hash
from fruitfly_agent.lab.improvement.assessment.joint import assess_batch
from fruitfly_agent.lab.improvement.assessment.promotion import compare_candidates
from tests.support.task_sets import collection
from tests.support.pipeline import fixture, version


class JointAssessmentTests(unittest.TestCase):
    def fixture(self):
        a, _ = collection('a', 1)
        b, _ = collection('b', 3)
        snapshot = TaskSetSnapshot((*a.entries, *b.entries))
        batch = EvaluationBatch(snapshot.snapshot_id, tuple(e.key for e in snapshot.entries))
        _, harness = fixture()
        trials = []
        for i, entry in enumerate(snapshot.entries):
            record = ExecutionRecord('run-' + str(i), entry.task.task_id, entry.task.material_id,
                harness.snapshot_id, version().state, version().harness, 'completed', model_calls=1)
            trials.append(TrialResult(entry.key, 0, record, Measurement(record.run_id, 'fixture-score', float(i == 0))))
        return snapshot, batch, trials, harness

    def test_task_macro_and_collection_macro_have_distinct_explicit_meaning(self):
        snapshot, batch, trials, harness = self.fixture()
        settings = MultiTaskSettings()
        self.assertEqual(assess_batch(snapshot, batch, trials, settings.evaluation).score, .5)
        task = MultiTaskSettings.from_dict({'evaluation': {'aggregation': 'task-macro'}})
        self.assertEqual(assess_batch(snapshot, batch, trials, task.evaluation).score, .25)
        weighted = MultiTaskSettings.from_dict({'evaluation': {'weights': {'a': 3, 'b': 1}}})
        self.assertEqual(assess_batch(snapshot, batch, trials, weighted.evaluation).score, .75)

    def test_zero_is_valid_and_missing_error_or_wrong_policy_cannot_shrink_the_denominator(self):
        snapshot, batch, trials, harness = self.fixture()
        settings = MultiTaskSettings()
        for changed in (trials[:-1], [*trials[:-1], replace(trials[-1], measurement=None)],
                [*trials[:-1], replace(trials[-1], record=replace(trials[-1].record, status='error'))],
                [*trials[:-1], replace(trials[-1], measurement=replace(trials[-1].measurement, policy_id='wrong'))]):
            self.assertIsNone(assess_batch(snapshot, batch, changed, settings.evaluation).score)
        with self.assertRaises(ValueError): assess_batch(snapshot, batch, [*trials, trials[0]], settings.evaluation)

    def test_comparison_refuses_different_task_batches(self):
        snapshot, batch, trials, harness = self.fixture()
        settings = MultiTaskSettings()
        before = CandidateEvaluation('before', harness.snapshot_id, version().harness, batch, tuple(trials),
            assess_batch(snapshot, batch, trials, settings.evaluation))
        after = replace(before, evaluation_id='after', batch=replace(batch, phase='selection'))
        with self.assertRaises(ValueError): compare_candidates(before, after, settings.promotion)
