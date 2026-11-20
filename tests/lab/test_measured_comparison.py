from contextlib import asynccontextmanager
from dataclasses import replace
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase

from fruitfly_agent.improvement.contracts.activities import ActivitySpec
from fruitfly_agent.improvement.contracts.assessment import AssessmentUnavailable
from fruitfly_agent.improvement.contracts.execution import ExecutionRecord
from fruitfly_agent.improvement.contracts.research import ResearchBatch
from fruitfly_agent.improvement.contracts.stages import StageInputs
from fruitfly_agent.improvement.contracts.tasks import Resource, TaskMaterial
from fruitfly_agent.improvement.contracts.versions import content_hash
from fruitfly_agent.lab.improvement.stages.compare import compare


class MeasuredComparisonTest(IsolatedAsyncioTestCase):
    async def test_default_mode_retains_model_judgments_and_unavailable_tasks(self):
        tasks = (TaskMaterial('available', 'Instruction'), TaskMaterial('missing', 'Instruction'))
        resources = tuple(Resource(name, content_hash(name)) for name in ('before', 'after'))
        result = {}

        async def evaluate(task, records, services):
            if task.task_id == 'missing':
                raise AssessmentUnavailable('No retained evidence')
            return {'summary': 'Comparable'}, content_hash('judgment')

        @asynccontextmanager
        async def services():
            yield None

        def put(path, payload):
            result.update(payload)
            return Resource(path, content_hash(path))

        ports = SimpleNamespace(read_batch=lambda _: ResearchBatch(tasks, ()), put=put,
                                create_services=services,
                                assessor=lambda _: SimpleNamespace(evaluator=SimpleNamespace(evaluate=evaluate)))
        await compare(ports, ActivitySpec('compare', 'research-compare-v1'), StageInputs(batches=resources))
        self.assertEqual(result['method'], 'model')
        self.assertEqual(result['coverage'], {'tasks': 2, 'judged': 1})
        self.assertEqual(result['judgments'][1]['status'], 'unavailable')

    async def test_pairing_uses_planned_runs_and_never_constructs_services(self):
        task = TaskMaterial('task', 'Instruction')
        state = content_hash('state')
        conditions = content_hash('conditions')
        scorer = content_hash('scorer')
        policy = content_hash('policy')
        resources = tuple(Resource(name, content_hash(name)) for name in ('before', 'after'))

        def batch(name, value, status):
            record = ExecutionRecord(name, task.task_id, task.material_id, content_hash(name),
                                     state, conditions, status)
            observation = {'run_id': name, 'scorer_id': scorer, 'outcome_policy_id': policy,
                           'name': 'reward', 'attempt': 0, 'value': value, 'eligible': True,
                           'semantics': {'outcome': 'met' if value else 'unmet'}}
            observation['semantics']['scope'] = 'execution'
            return ResearchBatch((task,), (record,), (observation,))

        batches = {resources[0]: batch('before', 0, 'completed'),
                   resources[1]: batch('after', 1, 'completed')}
        result = {}

        def put(path, payload):
            result.update(payload)
            return Resource(path, content_hash(path))

        ports = SimpleNamespace(read_batch=batches.__getitem__, put=put)
        manifest = {'pairs': [{'task_id': 'task', 'attempt': 0, 'before': 'before', 'after': 'after'}],
                    'metric': 'reward', 'direction': 'max', 'scorer_id': scorer,
                    'outcome_policy_id': policy, 'minimum_gain': 0, 'maximum_regression_rate': 0}
        inputs = StageInputs(batches=resources)

        async def run():
            spec = ActivitySpec('compare', 'research-compare-v1', parameters={'measured_policy': manifest})
            await compare(ports, spec, inputs)

        await run()
        self.assertEqual(result['conclusion'], 'better')
        self.assertEqual(result['mean_gain'], 1)
        candidate = batches[resources[1]]
        batches[resources[1]] = replace(candidate, records=(replace(candidate.records[0],
            initial_state_id=content_hash('different initial state')),))
        await run()
        self.assertEqual(result['conclusion'], 'insufficient')
        self.assertFalse(result['pairs'][0]['comparable'])
        self.assertIsNone(result['pairs'][0]['gain'])
        batches[resources[1]] = replace(candidate, observations=(
            {**candidate.observations[0], 'scorer_id': content_hash('different scorer')},))
        await run()
        self.assertEqual(result['conclusion'], 'insufficient')
        self.assertFalse(result['pairs'][0]['after']['attributed'])
        batches[resources[1]] = batch('after', 1, 'error')
        await run()
        self.assertEqual(result['conclusion'], 'insufficient')
        self.assertEqual(result['pairs'][0]['after']['raw'], 1)
        self.assertIsNone(result['pairs'][0]['after']['value'])
        manifest['pairs'].append({'task_id': 'task', 'attempt': 1, 'before': None, 'after': None})
        await run()
        self.assertEqual(result['coverage']['planned'], 2)
