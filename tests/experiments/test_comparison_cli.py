"""Default compare publishes portable native reports without constructing models."""
import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import yaml

from fruitfly_agent.experiments.cli import parser
from fruitfly_agent.experiments.operations.step import dispatch
from fruitfly_agent.improvement.contracts.execution import ExecutionRecord
from fruitfly_agent.improvement.contracts.observations import BatchManifest, PlannedAttempt, MeasurementObservation
from fruitfly_agent.improvement.contracts.research import ResearchBatch, ObservationSemantics
from fruitfly_agent.improvement.contracts.tasks import TaskMaterial
from fruitfly_agent.improvement.contracts.versions import content_hash
from tests.support.experiments import workspace


class ComparisonCliTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_compare_selects_explicit_subset_and_exports_without_manual_policy(self):
        identity = content_hash('fixed backend')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            path = workspace(root)
            authored = {'research': {'id': 'native-compare', 'output_root': '../study'},
                        'baseline': yaml.safe_load(path.read_text())['baseline'],
                        'stages': {}, 'next': {'stage': 'import'}}
            args = parser().parse_args(['improvement', 'step', '--config', str(path)])
            with patch('fruitfly_agent.providers.registry.ProviderRegistry.create',
                       side_effect=AssertionError('deterministic compare constructed Provider')):
                for side, count, value in [('before', 3, 0), ('after', 2, 1)]:
                    tasks = tuple(TaskMaterial('task-' + str(i), 'Do ' + str(i)) for i in range(count))
                    records = tuple(ExecutionRecord(side + str(i), t.task_id, t.material_id,
                        content_hash(side), identity, identity, 'completed') for i, t in enumerate(tasks))
                    observations = [BatchManifest(tuple(PlannedAttempt(t.task_id, 0) for t in tasks)).to_dict()]
                    observations += [MeasurementObservation(r.run_id, r.task_id, 0, 'reward', value, True,
                        ObservationSemantics('met' if value else 'unmet', 'higher'), identity, identity,
                        identity, comparison={'material': r.material_id, 'conditions': identity,
                            'initial_state': identity}).to_dict() for r in records]
                    (root / (side + '.json')).write_text(json.dumps(ResearchBatch(tasks, records, tuple(observations)).to_dict()))
                    authored['stages']['import'] = {'source': 'batch', 'path': '../' + side + '.json', 'publish_as': side}
                    path.write_text(yaml.safe_dump(authored))
                    await dispatch(args, root)
                authored['next']['stage'] = 'compare'
                authored['stages']['compare'] = {'inputs': {'batches': [{'artifact': 'before'}, {'artifact': 'after'}]}}
                path.write_text(yaml.safe_dump(authored))
                with self.assertRaisesRegex(ValueError, 'task-attempt scopes differ'):
                    await dispatch(args, root)
                authored['stages']['compare']['task_scope'] = {'artifact': 'after'}
                path.write_text(yaml.safe_dump(authored))
                result = await dispatch(args, root)
            published = Path(result['bundle']).parent
            report = json.loads((published / 'comparison.json').read_text())
            self.assertEqual(report['coverage']['excluded'], {'before': 1, 'after': 0})
            self.assertEqual(report['conclusion'], 'better')
            self.assertEqual(report['usage']['comparison_model_calls'], 0)
            self.assertIn('Gain (percentage points)', (published / 'summary.md').read_text())
            self.assertEqual(len(list(csv.DictReader((published / 'tasks.csv').read_text().splitlines()))), 2)
            self.assertTrue((published / 'metrics.csv').is_file())
