"""Exact prepared subsets preserve task content and validate coverage before execution."""
from dataclasses import replace
import unittest
from fruitfly_eval.contracts import EvaluationRequest
from fruitfly_eval.task_selection import select_prepared_tasks


class PreparedSelectionTests(unittest.TestCase):
    def test_legacy_request_roundtrip_and_explicit_names(self):
        old = {'runtime': {'working_directory': '.', 'config_path': None, 'profile': None},
            'benchmark': {'id': 'terminal-bench-4', 'variant': 'full'},
            'execution': {'attempts': 1, 'concurrency': 1, 'timeout_seconds': 3600}}
        request = EvaluationRequest.from_dict(old)
        self.assertEqual(request.to_dict(), old)
        named = replace(request, benchmark=replace(request.benchmark, task_names=('task-b',)))
        self.assertEqual(EvaluationRequest.from_dict(named.to_dict()), named)
        for names in ('task-a', ['task-a', 'task-a'], [True]):
            with self.subTest(names=names), self.assertRaises(ValueError):
                EvaluationRequest.from_dict({**old, 'benchmark': {**old['benchmark'], 'task_names': names}})

    def test_subset_is_an_exact_copy_with_original_parent_identity(self):
        original = {'id': 'immutable-parent', 'tasks': [{'id': 'task-a', 'path': '/a'}, {'id': 'task-b', 'path': '/b'}]}
        result = select_prepared_tasks(original, ('task-b',))
        self.assertEqual(result['tasks'], [{'id': 'task-b', 'path': '/b'}])
        self.assertEqual(result['parent_preparation_id'], 'immutable-parent')
        result['tasks'][0]['path'] = 'changed-copy'
        self.assertEqual(original['tasks'][1]['path'], '/b')
        with self.assertRaises(ValueError): select_prepared_tasks(original, ('missing',))
        with self.assertRaises(ValueError): select_prepared_tasks(original, ('task-a', 'task-a'))
