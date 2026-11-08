"""Public named inputs reject missing stage material without score requirements."""
import unittest
from fruitfly_agent.improvement.contracts.stages import StageInputs
from fruitfly_agent.improvement.contracts.tasks import Resource


class StageInputTests(unittest.TestCase):
    def setUp(self):
        self.resource = Resource('batch.json', 'sha256:' + 'a' * 64)

    def test_round_trip_and_detach_caller_sequence(self):
        batches = [self.resource]
        value = StageInputs(batches=batches)
        batches.clear()
        self.assertEqual(value.batches, (self.resource,))
        self.assertEqual(StageInputs.from_dict(value.to_dict()), value)

    def test_required_inputs_are_local_to_stage(self):
        batch = StageInputs(batches=(self.resource,))
        for stage in ('organize', 'assess'):
            self.assertIs(batch.validate_for(stage), batch)
        with self.assertRaisesRegex(ValueError, 'harness'):
            batch.validate_for('propose')
        StageInputs(harness=self.resource, batches=(self.resource,)).validate_for('propose')
        StageInputs(harness=self.resource).validate_for('execute')
        with self.assertRaisesRegex(ValueError, 'two batches'):
            batch.validate_for('compare')

    def test_unknown_fields_and_untyped_resources_are_rejected(self):
        with self.assertRaises(ValueError):
            StageInputs.from_dict({'score': 1})
        with self.assertRaises(TypeError):
            StageInputs(evidence=('batch.json',))
