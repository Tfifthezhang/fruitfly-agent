"""Compact facts preserve scopes without embedding execution evidence bodies."""
from dataclasses import replace
import json
import unittest

from fruitfly_agent.improvement.contracts.tasks import TaskMaterial, Resource
from fruitfly_agent.improvement.contracts.facts import UsageFact
from fruitfly_agent.improvement.execution.facts import receipt_facts
from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts
from fruitfly_agent.lab.improvement.evidence.summaries import execution_summary
from tests.support.stages import proposal_fixture, Runner


class ExecutionSummaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_projection_keeps_unknowns_conditions_and_separate_accounting_scopes(self):
        _, plan, harness, _ = proposal_fixture()
        task = TaskMaterial('summary-task', 'Inspect')
        record = await Runner().execute(plan, task, harness)
        record = replace(record, model_calls=None)
        unknown = execution_summary(record, None)
        self.assertIsNone(unknown['elapsed_seconds'])
        self.assertIsNone(unknown['model_calls'])
        self.assertIsNone(unknown['diagnostics_complete'])
        self.assertEqual(unknown['conditions_id'], record.conditions_id)
        facts = receipt_facts(record, MemoryArtifacts(), usage=(
            UsageFact('tool_calls', 'turn', 2, 'last model round'),
            UsageFact('tool_calls', 'execution', 30, 'all model rounds')),
            counters=(('tool_started', 30),), elapsed_seconds=42.)
        summary = execution_summary(record, facts)
        self.assertEqual([(v['scope'], v['used']) for v in summary['usage']], [('turn', 2), ('execution', 30)])
        self.assertEqual(summary['counters']['tool_started'], 30)
        self.assertEqual(summary['elapsed_seconds'], 42.)

    async def test_summary_size_does_not_grow_with_output_or_resource_paths(self):
        _, plan, harness, _ = proposal_fixture()
        record = await Runner().execute(plan, TaskMaterial('task', 'Inspect'), harness)
        artifacts = MemoryArtifacts()
        resources = tuple(Resource('large-directory/' + str(i) + '.txt', artifacts.put(b'body')) for i in range(200))
        record = replace(record, output='PRIVATE_OUTPUT' * 1000, artifacts=resources)
        text = json.dumps(execution_summary(record, None))
        self.assertEqual(execution_summary(record, None)['evidence_count'], 200)
        self.assertNotIn('PRIVATE_OUTPUT', text)
        self.assertNotIn('large-directory', text)
        self.assertLess(len(text), 2000)
