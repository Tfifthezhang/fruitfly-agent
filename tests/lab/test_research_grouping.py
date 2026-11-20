from unittest import IsolatedAsyncioTestCase, TestCase

from fruitfly_agent.improvement.contracts.execution import ExecutionRecord
from fruitfly_agent.improvement.contracts.research import ResearchBatch
from fruitfly_agent.improvement.contracts.tasks import TaskMaterial
from fruitfly_agent.improvement.contracts.versions import content_hash
from fruitfly_agent.lab.improvement.grouping.publication import compose


class ResearchGroupingTests(TestCase):
    def setUp(self):
        self.tasks = tuple(TaskMaterial('task-' + str(index), 'Inspect output') for index in range(25))
        identity = content_hash('fixture')
        self.records = tuple(ExecutionRecord('run-' + task.task_id, task.task_id, task.material_id,
                                            identity, identity, identity, 'completed') for task in self.tasks)
        self.pool = ResearchBatch(self.tasks, self.records, (
            {'run_id': self.records[0].run_id, 'name': 'selected'},
            {'run_id': self.records[1].run_id, 'name': 'excluded'},
            {'name': 'global hints should be omitted'},
        ))
        self.source = content_hash('pool')

    def test_fixed_scope_excludes_unselected_runs_and_global_observations(self):
        task = self.tasks[0]
        selected, decision = compose(self.pool, self.source, {'method': 'fixed', 'batch_size': 1},
                                     0, [[task.task_id]])
        self.assertEqual(selected.tasks, (task,))
        self.assertEqual(selected.records, self.records[:1])
        self.assertEqual([item['name'] for item in selected.observations], ['selected'])
        self.assertEqual(decision['members'], [{'task_id': task.task_id, 'run_ids': [self.records[0].run_id]}])
        self.assertNotIn('settings', selected.to_dict())

    def test_random_positions_cover_large_pool_and_preserve_partial_tail(self):
        policy = {'method': 'random', 'batch_size': 12, 'seed': 99}
        groups = [compose(self.pool, self.source, policy, position, None) for position in range(3)]
        self.assertEqual([len(batch.tasks) for batch, _ in groups], [12, 12, 1])
        membership = [task for batch, _ in groups for task in batch.tasks]
        self.assertCountEqual(membership, self.tasks)
        self.assertEqual(groups[1], compose(self.pool, self.source, policy, 1, None))
        self.assertTrue(groups[2][1]['incomplete_group'])
        with self.assertRaisesRegex(ValueError, 'outside source pool'):
            compose(self.pool, self.source, policy, 3, None)

    def test_fixed_receipts_must_belong_to_the_declared_task(self):
        settings = {'method': 'fixed', 'batch_size': 1}
        member = {'task_id': self.tasks[0].task_id, 'run_ids': [self.records[0].run_id]}
        selected, _ = compose(self.pool, self.source, settings, 0, [[member]])
        self.assertEqual(selected.records, self.records[:1])
        member['run_ids'] = [self.records[1].run_id]
        with self.assertRaisesRegex(ValueError, 'outside its task grant'):
            compose(self.pool, self.source, settings, 0, [[member]])

    def test_material_policy_never_drops_a_selected_member(self):
        from fruitfly_agent.improvement.contracts.tasks import Resource
        from fruitfly_agent.lab.improvement.evidence_selection.methods.focused import FocusedGroupSelector

        resources = {record.run_id: (Resource('trace.jsonl', self.source, kind='trajectory'),
                                    Resource('outcome.json', self.source, kind='diagnostic'),
                                    Resource('extra.json', self.source, kind='diagnostic'))
                     for record in self.records}
        rows = [{'run_id': record.run_id, 'task_id': record.task_id} for record in self.records]
        plan = FocusedGroupSelector('trajectory-only').select(rows, resources=resources)
        self.assertEqual([item['run_id'] for item in plan['selected']], list(resources))
        self.assertTrue(all(item['material_paths'] == ['trace.jsonl'] for item in plan['selected']))
        self.assertEqual(plan['omitted_executions'], 0)
        focused = FocusedGroupSelector('focused').select(rows, resources=resources)
        self.assertEqual(focused['selected'][0]['material_paths'], ['trace.jsonl', 'outcome.json'])
        extended = FocusedGroupSelector('trajectory-only', ('termination',)).select(rows, resources=resources)
        self.assertEqual([item['run_id'] for item in extended['selected']], list(resources))
        self.assertEqual(extended['selected'][0]['material_reasons']['outcome.json'], ['termination'])
        self.assertNotEqual(extended['selector_id'], plan['selector_id'])

    def test_organization_units_keep_missing_members_and_continuity(self):
        import json
        from types import SimpleNamespace
        from fruitfly_agent.lab.improvement.organizer.methods.layered.scheduling import schedule

        index_path = 'context/executions/one/evidence/events.json'
        packet = {'cards': [
            {'task_id': 'no-receipt', 'executions': []},
            {'task_id': 'no-index', 'executions': [{'run_id': 'run-two', 'events': None}]},
            {'task_id': 'indexed', 'executions': [{'run_id': 'run-three', 'events': {
                'path': index_path, 'artifact_id': self.source}}]},
        ]}
        workspace = SimpleNamespace(read={index_path: json.dumps({
            'events': [{'event_id': str(event)} for event in range(5)],
        })}.__getitem__)
        units = schedule(packet, workspace, 2)
        self.assertEqual([unit['state'] for unit in units], [
            'missing_execution', 'missing_index', 'pending', 'pending', 'pending',
        ])
        self.assertEqual([unit['event_ids'] for unit in units[2:]], [('0', '1'), ('2', '3'), ('4',)])
        self.assertEqual([unit['previous_event'] for unit in units[2:]], [None, '1', '3'])
        self.assertEqual(units, schedule(packet, workspace, 2))

    def test_authorized_group_size_changes_membership_without_changing_baseline(self):
        from fruitfly_agent.lab.improvement.components.text import TextComponentAdapter
        from fruitfly_agent.lab.improvement.grouping.improvement import GroupingTarget, candidate_group
        from tests.support.configuration import component_parameters, with_component_parameters

        baseline = {'settings': {'method': 'random', 'batch_size': 1, 'seed': 99}}
        target = GroupingTarget(baseline)
        document = TextComponentAdapter(target, target.component_kind).snapshot()
        authored = component_parameters(document)
        authored['settings']['batch_size'] = 3
        changed = with_component_parameters(document, authored)
        arguments = {'options': {'editable_fields': ['parameters.settings.batch_size']}, 'position': 0}
        original, first = candidate_group(self.pool, self.source, baseline, document, **arguments)
        result, second = candidate_group(self.pool, self.source, baseline, changed, **arguments)
        self.assertEqual([len(original.tasks), len(result.tasks)], [1, 3])
        self.assertNotEqual(first['policy_id'], second['policy_id'])
        self.assertEqual(baseline['settings']['batch_size'], 1)
        authored['settings']['seed'] = 100
        with self.assertRaisesRegex(ValueError, 'protected grouping fields'):
            candidate_group(self.pool, self.source, baseline,
                            with_component_parameters(document, authored), **arguments)

    def test_all_contrast_methods_share_an_explicit_table(self):
        from fruitfly_agent.lab.improvement.grouping.features import frozen_features

        table = frozen_features(self.pool, lambda _: self.fail('no event index was granted'))
        for method in ('failure', 'text', 'trajectory', 'matched', 'diverse'):
            with self.subTest(method=method):
                policy = {'method': method, 'batch_size': 3, 'seed': 5}
                selected, decision = compose(self.pool, self.source, policy, 0, None, features=table)
                self.assertEqual(len(selected.tasks), 3)
                self.assertEqual(decision['settings']['method'], method)
                self.assertNotIn('features', selected.to_dict())


class GroupExtractionTests(IsolatedAsyncioTestCase):
    async def test_unit_observations_must_reference_its_frozen_event_grant(self):
        import json
        from types import SimpleNamespace
        from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts
        from fruitfly_agent.lab.improvement.evidence.access import EvidenceAccess
        from fruitfly_agent.lab.improvement.evidence.resources import ReferenceWorkspace
        from fruitfly_agent.lab.improvement.organizer.methods.layered.extraction import extract
        from tests.support.stages import proposal_fixture

        _, _, baseline, _ = proposal_fixture()
        artifacts = MemoryArtifacts()
        from fruitfly_agent.lab.improvement.evidence.tools import evidence_tools

        index_path = 'context/evidence/events.json'
        source_path = 'context/trace.jsonl'
        source = artifacts.put('界failure details\noutside unit'.encode())
        index_artifact = artifacts.put(json.dumps({'events': [
            {'event_id': 'local', 'kind': 'toolCall', 'source_path': 'trace.jsonl',
             'artifact_id': source, 'start': 1, 'end': 16},
            {'event_id': 'other', 'kind': 'toolResult', 'source_path': 'trace.jsonl',
             'artifact_id': source, 'start': 17, 'end': 29},
        ]}).encode())
        task_input = {'artifact_id': artifacts.put(b'Task instruction')}
        workspace = ReferenceWorkspace(artifacts=artifacts,
                                       references={index_path: index_artifact, source_path: source},
                                       baseline=baseline, files={}, writable_ids=(), access=EvidenceAccess())
        unit = {'task_id': 'task', 'run_id': 'run', 'event_ids': ['local'],
                'previous_event': None, 'event_index': {'path': index_path, 'artifact_id': index_artifact}}
        user_event = 'local'

        async def run(mission, local, services, **kwargs):
            self.assertNotIn(index_path, local.paths())
            self.assertNotIn(source_path, local.paths())
            self.assertEqual(local.read('context/task.md'), b'Task instruction')
            event, = json.loads(local.read('context/unit.json'))['events']
            self.assertEqual(event['event_id'], 'local')
            read = next(tool for tool in evidence_tools(local) if tool.name == 'read')
            result = await read.execute(SimpleNamespace(args={'path': event['source']['path']}))
            self.assertEqual(json.loads(result.content[0].text)['text'], 'failure details')
            with self.assertRaisesRegex(ValueError, 'grant'):
                await read.execute(SimpleNamespace(args={'path': source_path}))
            return json.dumps([{'event_id': user_event, 'observation': 'A tool was called'}])

        session = SimpleNamespace(session=run)
        services = SimpleNamespace(record=lambda *args, **kwargs: None)
        accepted = await extract(session, 'Inspect metadata', 'Read only', unit, workspace, task_input, services)
        self.assertEqual(accepted[0]['event_id'], 'local')
        user_event = 'other'
        with self.assertRaisesRegex(ValueError, 'event grant'):
            await extract(session, 'Inspect metadata', 'Read only', unit, workspace, task_input, services)

        index = json.loads(artifacts.read(index_artifact))
        index['events'][1].update(start=1, end=16)
        workspace.references[index_path] = artifacts.put(json.dumps(index).encode())
        unit['event_index']['artifact_id'] = workspace.references[index_path]

        async def read_shared(mission, local, services, **kwargs):
            event, = json.loads(local.read('context/unit.json'))['events']
            self.assertIsNone(event['source'])
            self.assertEqual(event['source_status'], 'shared_with_other_unit')
            return '[]'

        accepted = await extract(SimpleNamespace(session=read_shared), 'Inspect metadata', 'Read only',
                                 unit, workspace, task_input, services)
        self.assertEqual(accepted, [])

    async def test_extraction_request_ceiling_reserves_synthesis_even_after_tool_use(self):
        from fruitfly_agent.core.config import AgentLoopConfig
        from fruitfly_agent.improvement.stages.services import StageServices
        from fruitfly_agent.lab.improvement.evidence import EvidenceWorkspace, MemoryArtifacts
        from fruitfly_agent.lab.improvement.evidence.session import EvidenceSession
        from tests.support.faux_provider import FauxProvider
        from tests.support.stages import proposal_fixture

        _, plan, baseline, _ = proposal_fixture()
        provider = FauxProvider()
        provider.respond_tool_call('read', {'path': 'source.txt'})
        provider.respond_text('Synthesis can still finish')
        workspace = EvidenceWorkspace(baseline=baseline, files={'source.txt': b'observed'}, writable_ids=())
        session = EvidenceSession(AgentLoopConfig(provider), MemoryArtifacts())
        async with StageServices(plan) as services:
            with self.assertRaisesRegex(RuntimeError, 'evidence_request_budget_exhausted'):
                await session.session('Extract', workspace, services, model_request_ceiling=1)
            self.assertEqual(1, len(provider.calls))
            self.assertEqual(1, workspace.access.budget['model_requests'])
            self.assertEqual('Synthesis can still finish', await session.session('Synthesize', workspace, services))
            self.assertEqual(2, len(provider.calls))
