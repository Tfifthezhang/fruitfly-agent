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

    def test_statistics_keep_unknown_denominators_and_source_declared_outcomes(self):
        from fruitfly_agent.lab.improvement.evidence.statistics import batch_statistics
        rows = [
            {'status': 'completed', 'observations': [{'name': 'loss', 'value': 0,
                'semantics': {'outcome': 'met', 'direction': 'lower'}}], 'counters': {'tool_denied': 0}},
            {'status': 'error', 'observations': [{'name': 'score', 'value': 100,
                'semantics': {'outcome': 'unknown'}}], 'counters': {}},
            {'status': 'completed', 'observations': [{'name': 'accuracy', 'value': .1,
                'semantics': {'outcome': 'unmet', 'direction': 'higher'}}], 'counters': {}}]
        result = batch_statistics(rows, [{'name': 'environment', 'value': 'fixture'}])
        self.assertEqual(3, result['population_count'])
        self.assertEqual({'population_count': 3, 'known_count': 1, 'unknown_count': 2,
            'counts': {'0': 1}}, result['counters']['tool_denied'])
        self.assertEqual(1, result['outcomes']['unknown_count'])
        self.assertEqual({'met': 1, 'unmet': 1}, result['outcomes']['counts'])
        self.assertEqual('environment', result['batch_observations'][0]['name'])

    def test_inspection_distinguishes_search_from_read_and_merges_unicode_ranges(self):
        from fruitfly_agent.lab.improvement.evidence.access import EvidenceAccess
        access = EvidenceAccess()
        access.provided('text', 'abc', offset=0, reading_kind='search')
        access.provided('text', 'é中文', offset=2)
        access.provided('text', 'de', offset=4)
        reading = access.inspection()['paths']['text']
        self.assertEqual([(0, 3)], reading['search'])
        self.assertEqual([(2, 6)], reading['read'])

    def test_supplied_single_summary_attributes_only_its_execution(self):
        from fruitfly_agent.lab.improvement.evidence.access import EvidenceAccess
        access = EvidenceAccess(('a', 'b'))
        access.provided('context/summaries/a.json', '{"run_id":"a"}')
        self.assertEqual({'a'}, access.supplied)

    def test_execution_navigation_excludes_large_observations_but_links_full_summary(self):
        from types import SimpleNamespace
        from fruitfly_agent.lab.improvement.evidence.executions import execution_page
        rows = [{'run_id': 'one', 'task_id': 'task', 'status': 'error',
                 'model_calls': None, 'observations': [{'body': 'x' * 50000}]}]
        workspace = SimpleNamespace(read=lambda _: json.dumps(rows))
        result = execution_page(workspace, cursor=0, limit=8, compact=True)
        self.assertEqual(result['executions'][0]['model_calls'], None)
        self.assertEqual(result['executions'][0]['summary_path'], 'context/summaries/one.json')
        self.assertNotIn('observations', result['executions'][0])
        self.assertIsNone(result['next_cursor'])

    def test_execution_lookup_returns_one_complete_observation_record(self):
        from types import SimpleNamespace
        from fruitfly_agent.lab.improvement.evidence.executions import execution_page
        rows = [{'run_id': 'one', 'observations': [{'reward': None}]},
                {'run_id': 'two', 'observations': [{'reward': 1}]}]
        page = execution_page(SimpleNamespace(read=lambda _: json.dumps(rows)),
                              cursor=0, limit=8, run_id='one')
        self.assertEqual(page['total'], 1)
        self.assertEqual(page['executions'][0]['observations'], [{'reward': None}])

    def test_child_usage_uses_attributed_sessions_once(self):
        from fruitfly_agent.run.storage.research_bundles import role_usage
        class Store:
            def read_bytes(self, key):
                return payloads[key]
        child = json.dumps({'kind': 'runRecord', 'event': 'end', 'data': {
            'provider_attempt_count': 3, 'usage': {'inputTokens': 50}}}).encode()
        followup = json.dumps({'kind': 'runRecord', 'event': 'end', 'run_id': 'followup',
                               'data': {'provider_attempt_count': 2, 'usage': {'inputTokens': 20}}}).encode()
        child += b'\n' + followup
        payloads = {'child': child,
                    'event': json.dumps({'event': 'research-child-session', 'artifact_id': 'child'}).encode(),
                    'trace': json.dumps({'events': [{'artifact_id': 'event'}, {'artifact_id': 'event'}]}).encode()}
        usage = role_usage(Store(), 'trace')
        self.assertEqual(usage['children']['sessions'], 1)
        self.assertEqual(usage['children']['provider_attempts_observed'], 5)
        self.assertEqual(usage['combined_reported_token_subtotals']['inputTokens'], 70)
