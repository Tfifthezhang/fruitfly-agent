"""Research plans retain missing attempts and reject misattributed measurements."""
from dataclasses import replace
import unittest

from fruitfly_agent.improvement.contracts.observations import BatchManifest, MeasurementObservation, PlannedAttempt
from fruitfly_agent.improvement.contracts.research import ObservationSemantics, ResearchBatch
from fruitfly_agent.improvement.contracts.execution import ExecutionRecord
from fruitfly_agent.improvement.contracts.tasks import TaskMaterial
from fruitfly_agent.improvement.contracts.versions import content_hash


class ResearchObservationTests(unittest.TestCase):
    def test_partial_execution_retains_the_planned_denominator(self):
        task = TaskMaterial('task', 'Work')
        identity = content_hash('identity')
        record = ExecutionRecord('run', task.task_id, task.material_id, identity, identity, identity, 'error')
        manifest = BatchManifest((PlannedAttempt('task', 0), PlannedAttempt('task', 1)))
        observation = MeasurementObservation('run', 'task', 0, 'reward', 0, False,
            ObservationSemantics(), None, identity, identity, 'Execution interrupted')
        batch = ResearchBatch((task,), (record,), (manifest.to_dict(), observation.to_dict()))
        restored = ResearchBatch.from_dict(batch.to_dict())
        self.assertEqual(len(BatchManifest.from_dict(restored.observations[0]).planned), 2)
        self.assertFalse(MeasurementObservation.from_dict(restored.observations[1]).eligible)
        for changed in (replace(observation, run_id='missing'), replace(observation, attempt=2)):
            with self.assertRaises(ValueError):
                ResearchBatch((task,), (record,), (manifest.to_dict(), changed.to_dict()))
        with self.assertRaises(ValueError):
            ResearchBatch((task,), (record,), (observation.to_dict(), observation.to_dict()))

    def test_unknown_measurements_never_claim_acceptance(self):
        identity = content_hash('policy')
        for value in (True, float('nan'), float('inf')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                MeasurementObservation('run', 'task', 0, 'reward', value, False,
                    ObservationSemantics(), None, identity, None)
        with self.assertRaises(ValueError):
            MeasurementObservation('run', 'task', 0, 'reward', 1, False,
                ObservationSemantics(outcome='met'), None, identity, None)
        with self.assertRaises(ValueError):
            BatchManifest((PlannedAttempt('task', 0), PlannedAttempt('task', 0)))
