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
                {'batch.json', 'overview.json', 'executions.json', 'coverage.json'})
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
                    'content': [{'type': 'text', 'text': 'Delivered'}]}}]
            (agent / 'session.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in messages))
            (trial / 'result.json').write_text(json.dumps({'task_name': 'fixture',
                'exception_info': {'exception_type': 'AgentTimeoutError'}, 'verifier_result': {'rewards': {'reward': 1}}}))
            private = trial / 'verifier'; private.mkdir(); (private / 'answer').write_text('PRIVATE SENTINEL')
            artifacts = MemoryArtifacts()
            batch = import_history(root, artifacts)
            self.assertEqual(batch.tasks[0].instruction, 'Do the task')
            self.assertEqual(batch.records[0].status, 'error')
            self.assertEqual(batch.observations[0]['value'], {'reward': 1})
            self.assertTrue(all(b'PRIVATE SENTINEL' not in v for v in artifacts.values.values()))

    async def test_cli_inspection_requires_neither_configuration_nor_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            args = parser().parse_args(['--cwd', directory, 'improvement', 'inspect', '--study', 'study'])
            with patch('fruitfly_agent.providers.registry.ProviderRegistry.create', side_effect=AssertionError('Provider constructed')):
                # dispatch is synchronous; use the async operation directly here.
                from fruitfly_agent.experiments.operations.research import dispatch as operation
                result = await operation(args, Path(directory))
            self.assertEqual(result['attempts'], {})
