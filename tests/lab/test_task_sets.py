"""Task-set identities, score meaning and deterministic coverage are explicit."""
from dataclasses import replace
import unittest

from fruitfly_agent.improvement.contracts.task_sets import TaskSetSnapshot, ScoreSpec
from fruitfly_agent.lab.improvement.task_sets import MultiTaskSettings, sample_batch
from fruitfly_agent.lab.improvement.task_sets.execution import minimum_budget as task_set_minimum_budget
from tests.support.task_sets import collection


class TaskSetTests(unittest.TestCase):
    def test_sampling_covers_each_collection_and_eventually_each_task(self):
        a, _ = collection('a', 5)
        b, _ = collection('b', 3)
        snapshot = TaskSetSnapshot((*a.entries, *b.entries))
        settings = MultiTaskSettings.from_dict({'sampling': {'batch_size': 3}})
        batches = [sample_batch(snapshot, settings.sampling, i) for i in range(8)]
        self.assertEqual(batches, [sample_batch(snapshot, settings.sampling, i) for i in range(8)])
        self.assertEqual(set().union(*(set(b.task_keys) for b in batches)), {e.key for e in snapshot.entries})
        self.assertTrue(all(any(k.startswith('a-') for k in b.task_keys)
            and any(k.startswith('b-') for k in b.task_keys) for b in batches))
        with self.assertRaises(ValueError):
            sample_batch(snapshot, replace(settings.sampling, batch_size=1), 0)

    def test_duplicate_materials_and_cross_partition_groups_are_rejected(self):
        a, _ = collection('a')
        with self.assertRaises(ValueError): TaskSetSnapshot((*a.entries, a.entries[0]))
        with self.assertRaises(ValueError):
            TaskSetSnapshot((replace(a.entries[0], group_id='related'),
                replace(a.entries[1], group_id='related', partition='confirmation')))
        with self.assertRaises(ValueError):
            TaskSetSnapshot((a.entries[0], replace(a.entries[1], origin_id=a.entries[0].origin_id)))

    def test_selection_keeps_each_collection_when_only_some_have_private_validation(self):
        a, _ = collection('benchmark', 2)
        b, _ = collection('daily', 1, partition='selection')
        snapshot = TaskSetSnapshot((*a.entries, *b.entries))
        self.assertEqual({e.collection_id for e in snapshot.selection_entries()}, {'benchmark', 'daily'})

    def test_minimum_budget_protects_full_selection_and_repeated_leaf_execution(self):
        a, _ = collection('benchmark', 2, limit=3)
        b, _ = collection('daily', 1, limit=5, partition='selection')
        snapshot = TaskSetSnapshot((*a.entries, *b.entries))
        settings = MultiTaskSettings.from_dict({'sampling': {'batch_size': 1}, 'execution': {'attempts': 2}})
        # Two harnesses: one sampled task plus all three selection tasks, twice.
        self.assertEqual(task_set_minimum_budget(snapshot, settings), {'model': 64, 'execution': 16})

    def test_configuration_rejects_unused_fields_invalid_weights_and_candidate_parallelism(self):
        for raw in ({'unknown': {}}, {'execution': {'candidate_concurrency': 2}},
                    {'evaluation': {'weights': {'a': -1}}}, {'sampling': {'policy': 'fixed'}},
                    {'execution': {'concurrency': True}}, {'evaluation': {'aggregation': 'task-macro', 'weights': {'a': 1}}}):
            with self.subTest(raw=raw), self.assertRaises(ValueError): MultiTaskSettings.from_dict(raw)
        self.assertEqual(ScoreSpec('score', 0, 100, 'min').normalize(25), .75)
        with self.assertRaises(ValueError): ScoreSpec('score').normalize(2)
