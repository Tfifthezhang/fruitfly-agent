"""Retained batches flow through independent actions without execution or scores."""
from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fruitfly_agent.experiments.cli import parser, dispatch
from fruitfly_agent.improvement.contracts.research import ResearchBatch
from fruitfly_agent.improvement.contracts.assessment import AssessmentUnavailable
from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts
from fruitfly_agent.run.improvement.service import ResearchService
from fruitfly_agent.lab.improvement.stages.propose import proposal_request
from fruitfly_eval.improvement.history import import_history
from tests.support.stages import proposal_fixture, Runner


class ResearchServiceTests(unittest.IsolatedAsyncioTestCase):
    def test_eval_import_retains_unstarted_tasks_from_selected_preparation(self):
        from fruitfly_agent.improvement.contracts.observations import BatchManifest
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trial = root / 'artifacts/harbor/job/observed'
            (trial / 'agent').mkdir(parents=True)
            (trial / 'result.json').write_text(json.dumps({'task_name': 'first',
                'verifier_result': {'rewards': {'reward': 0}}}))
            (trial / 'agent/session.jsonl').write_text(json.dumps({'message': {
                'role': 'user', 'content': 'Work'}}) + '\n')
            (root / 'request.json').write_text(json.dumps({'execution': {'attempts': 2}}))
            (root / 'report.json').write_text(json.dumps({'benchmark': {'dataset': 'fixture'}}))
            (root / 'artifacts/harbor/preparation.json').write_text(json.dumps({'tasks': [
                {'id': 'first-id', 'name': 'first'}, {'id': 'unstarted-id', 'name': 'unstarted'}]}))
            batch = import_history(root, MemoryArtifacts())
            manifest = BatchManifest.from_dict(batch.observations[-1])
            self.assertEqual(manifest.scope_kind, 'retained-planned')
            self.assertEqual(len(manifest.planned), 4)
            self.assertEqual(len(batch.records), 1)
            self.assertEqual(len(batch.tasks), 2)
            self.assertIn('fixture:unstarted-id', dict(manifest.origins).values())

    async def test_measured_compare_reuses_frozen_inputs_without_a_model_role(self):
        from dataclasses import replace
        from fruitfly_agent.improvement.contracts.stages import StageInputs
        from fruitfly_agent.improvement.contracts.tasks import TaskMaterial
        from fruitfly_agent.improvement.contracts.versions import content_hash

        _, plan, baseline, runner = proposal_fixture()
        task = TaskMaterial('task', 'Compare the retained executions')
        before = await runner.execute(plan, task, baseline)
        after = replace(before, run_id='candidate-run', harness_id=content_hash('candidate'))
        scorer = content_hash('fixture scorer')
        policy = content_hash('fixture outcome policy')

        def recorded(receipt, value, outcome):
            return ResearchBatch((task,), (receipt,), (
                {'run_id': receipt.run_id, 'attempt': 0, 'name': 'reward', 'value': value,
                 'scorer_id': scorer, 'outcome_policy_id': policy, 'eligible': True,
                 'semantics': {'scope': 'execution', 'outcome': outcome}},)).to_dict()

        with tempfile.TemporaryDirectory() as directory:
            service = ResearchService(directory, 'study', MemoryArtifacts())
            service.revise({'comparison': 'measured'})
            batches = (service.put('before.json', recorded(before, 0, 'unmet')),
                       service.put('after.json', recorded(after, 1, 'met')))
            manifest = {'metric': 'reward', 'scorer_id': scorer, 'outcome_policy_id': policy,
                        'direction': 'max', 'minimum_gain': 0, 'maximum_regression_rate': 0,
                        'pairs': [{'task_id': task.task_id, 'attempt': 0,
                                   'before': before.run_id, 'after': after.run_id}]}
            named = StageInputs(batches=batches)
            result = await service.perform_named('compare', named, parameters={'measured_policy': manifest})
            self.assertEqual(service.read(result.outputs[0])['conclusion'], 'better')
            repeated = await service.perform_named('compare', named, parameters={'measured_policy': manifest})
            self.assertEqual(repeated, result)
            self.assertEqual(len(runner.calls), 1)

    async def test_named_batch_proposal_reads_multiple_failed_unscored_batches_without_execution(self):
        from dataclasses import replace
        from fruitfly_agent.improvement.contracts.stages import StageInputs
        from fruitfly_agent.improvement.contracts.tasks import TaskMaterial
        from fruitfly_agent.lab.improvement.editor.generators import GeneratorRegistry
        from fruitfly_agent.lab.improvement.editor.proposal import ProposalStage
        from tests.support.stages import RuleGenerator
        _, plan, baseline, runner = proposal_fixture()
        seen = []
        class Generator(RuleGenerator):
            supports_task_sets = True
            async def propose(self, request, services):
                seen.append(request)
                return await super().propose(request, services)
        generators = GeneratorRegistry(); generators.register('rule-generator', Generator)
        artifacts = MemoryArtifacts()
        with tempfile.TemporaryDirectory() as directory:
            service = ResearchService(directory, 'study', artifacts, plan=plan,
                proposal=ProposalStage(generators=generators, components=proposal_fixture()[0].components))
            service.revise({'fixture': 'unscored retained failures'})
            batches = []
            for index in range(2):
                task = TaskMaterial('task-' + str(index), 'Inspect partial task ' + str(index))
                record = replace(await runner.execute(plan, task, baseline), status='error')
                batches.append(service.put('batch-' + str(index) + '.json',
                    ResearchBatch((task,), (record,), ({'name': 'score', 'value': None},)).to_dict()))
            harness = service.put('harness.json', baseline.to_dict())
            result = await service.perform_named('propose', StageInputs(harness=harness, batches=tuple(batches)))
            self.assertEqual(len(seen), 1)
            self.assertEqual(len(seen[0].tasks), 2)
            self.assertEqual(len(seen[0].records), 2)
            self.assertEqual(len(runner.calls), 2, 'proposal must not run a baseline or candidate')
            self.assertEqual(len(service.read(result.outputs[0])['candidates']), 1)
            repeated = await service.perform_named('propose', StageInputs(harness=harness, batches=tuple(batches)))
            self.assertEqual(repeated, result)
            self.assertEqual(len(seen), 1)
            forged = StageInputs(harness=harness, batches=tuple(batches)).to_dict()
            with self.assertRaisesRegex(ValueError, 'artifact grant'):
                await service.perform('propose', (harness, batches[0]), parameters={'named_inputs': forged})
            self.assertEqual(len(seen), 1)
            class OtherGenerator(Generator):
                generator_id = 'other-rule'
            generators.register('other-rule', OtherGenerator)
            service.plan = replace(plan, generator_id='other-rule')
            await service.perform_named('propose', StageInputs(harness=harness, batches=tuple(batches)))
            self.assertEqual(len(seen), 2, 'changing the generator must produce a new activity')

    async def test_import_missing_feedback_then_batch_proposal_needs_no_reexecution(self):
        _, plan, baseline, _ = proposal_fixture()
        from fruitfly_agent.improvement.contracts.tasks import TaskMaterial
        task = TaskMaterial('task', 'Retained task')
        record = await Runner().execute(plan, task, baseline)
        batch = ResearchBatch((task,), (record,), ({'name': 'reward', 'value': None},))
        artifacts = MemoryArtifacts()
        class Unavailable:
            evaluator = type('Evaluator', (), {'context': ()})()
            async def assess(self, task, record):
                raise AssessmentUnavailable('historical facts unavailable')
        with tempfile.TemporaryDirectory() as directory:
            service = ResearchService(directory, 'study', artifacts, plan=plan,
                assessor=lambda services: Unavailable())
            service.revise({'editor': 'current'})
            imported = await service.perform('import', (service.put('batch.json', batch.to_dict()),))
            from fruitfly_agent.improvement.contracts.stages import StageInputs
            self.assertEqual({r.path for r in imported.outputs},
                {'batch.json', 'overview.json', 'executions.json', 'coverage.json', 'statistics.json'})
            overview = service.read(next(r for r in imported.outputs if r.path == 'overview.json'))
            self.assertEqual(overview['execution_count'], 1)
            assessed = await service.perform_named('assess', StageInputs(
                batches=tuple(r for r in imported.outputs if r.path == 'batch.json')))
            restored = ResearchBatch.from_dict(service.read(assessed.outputs[0]))
            self.assertEqual(restored.records[0].output, record.output)
            feedback = restored.records[0].artifacts[-1]
            self.assertEqual(json.loads(artifacts.read(feedback.artifact_id))['status'], 'unavailable')
            request = proposal_request(restored, plan, baseline)
            self.assertEqual(request.records[0].run_id, record.run_id)
            self.assertEqual(len(service.controller.state().attempts), 2)

    async def test_eval_import_keeps_reward_separate_from_timeout_and_excludes_verifier(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trial = root / 'artifacts/harbor/job/task'
            agent = trial / 'agent'; agent.mkdir(parents=True)
            messages = [{'type': 'message', 'message': {'role': 'user', 'content': 'Do the task'}},
                {'type': 'message', 'message': {'role': 'assistant', 'stopReason': 'stop',
                    'content': [{'type': 'text', 'text': 'Delivered'},
                                {'type': 'thinking', 'thinking': 'EXTENSION SENTINEL'},
                                {'type': 'image', 'data': 'EXTENSION SENTINEL'}]}},
                {'type': 'compaction', 'summary': 'EXTENSION SENTINEL'}]
            (agent / 'session.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in messages))
            (trial / 'result.json').write_text(json.dumps({'task_name': 'fixture',
                'exception_info': {'exception_type': 'AgentTimeoutError'}, 'verifier_result': {'rewards': {'reward': 1}}}))
            private = trial / 'verifier'; private.mkdir(); (private / 'answer').write_text('PRIVATE SENTINEL')
            artifacts = MemoryArtifacts()
            batch = import_history(root, artifacts)
            self.assertEqual(batch.tasks[0].instruction, 'Do the task')
            self.assertEqual(batch.records[0].status, 'error')
            self.assertEqual(batch.observations[0]['raw_value'], {'reward': 1})
            self.assertEqual(batch.observations[0]['value'], 1)
            self.assertFalse(batch.observations[0]['eligible'])
            self.assertEqual(batch.observations[0]['semantics']['outcome'], 'unknown')
            self.assertTrue(all(b'PRIVATE SENTINEL' not in v for v in artifacts.values.values()))
            scope = next(r for r in batch.records[0].artifacts if r.path == 'diagnostics/reading-scope.json')
            extensions = json.loads(artifacts.read(scope.artifact_id))['extensions']
            self.assertEqual({'thinking': 1, 'image': 1, 'compaction': 1},
                             {key: value['observed_count'] for key, value in extensions.items()})
            self.assertTrue(all(b'EXTENSION SENTINEL' not in v for v in artifacts.values.values()))

    async def test_cli_inspection_requires_neither_configuration_nor_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            args = parser().parse_args(['--cwd', directory, 'improvement', 'inspect', '--study', 'study'])
            with patch('fruitfly_agent.providers.registry.ProviderRegistry.create', side_effect=AssertionError('Provider constructed')):
                # dispatch is synchronous; use the async operation directly here.
                from fruitfly_agent.experiments.operations.research import dispatch as operation
                result = await operation(args, Path(directory))
            self.assertEqual(result['attempts'], {})
