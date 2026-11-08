"""Benchmark collections pass single selected tasks through existing Eval lifecycle."""
from fruitfly_eval.installation import installation_identity
from tests.support.configuration import profile_document
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

import yaml
from fruitfly_eval.improvement.task_sets import freeze
from fruitfly_agent.improvement.contracts.task_sets import TaskSetSnapshot
from fruitfly_agent.lab.improvement.task_sets import MultiTaskSettings
from fruitfly_agent.improvement.execution.batches import BatchEvaluator
from fruitfly_agent.lab.improvement.execution import ExecutionContext
from fruitfly_agent.improvement.stages.services import StageServices
from fruitfly_agent.improvement.contracts.plans import RunPlan
from fruitfly_agent.improvement.contracts.evaluation import EvaluationBatch
from fruitfly_agent.lab.improvement.components import ComponentRegistry, TextComponentAdapter
from fruitfly_agent.lab.base_prompt.target import BasePromptTarget
from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts
from fruitfly_agent.lab.improvement.assessment.joint import assess_batch
from tests.support.stages import version


class EvalCollectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_many_prepared_tasks_remain_individual_executions_with_private_grading_excluded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / '.fruitfly'; state.mkdir()
            config = state / 'default-config.yaml'
            config.write_text(yaml.safe_dump({'default_profile': 'baseline', 'profiles': {'baseline': profile_document(catalog='models.yaml', executor='fake')}}))
            (state / 'models.yaml').write_text('models: {}\n')
            request = root / 'request.json'
            request.write_text(json.dumps({'runtime': {'working_directory': str(root)},
                'benchmark': {'id': 'terminal-bench-4', 'variant': 'full'}}))
            host = root / 'host.yaml'; host.write_text('fixture host')
            tasks = []
            for name in ('a', 'b'):
                path = root / name; path.mkdir(); (path / 'instruction.md').write_text('Complete fixture ' + name)
                tasks.append({'id': 'fixture/' + name, 'path': str(path)})
            source = Path(__file__).resolve().parents[2]
            files = installation_identity(source)['files']
            prepared = {'id': 'prepared-fixture', 'tasks': tasks, 'runtime': {'installation': {'files': files}}}
            components = ComponentRegistry((TextComponentAdapter(BasePromptTarget('baseline'), 'system-prompt'),))
            plan = RunPlan('joint-eval', version(), ('base_prompt',))
            services = StageServices(plan)
            context = ExecutionContext(root, MemoryArtifacts(), components, None, None, None, plan=plan, services=services)
            context.runtime_config, context.runtime_profile = config, None
            names = []
            async def executor(evaluation, host_path, *, directory, output_root, emit):
                names.append(evaluation.benchmark.task_names)
                self.assertEqual(len(names[-1]), 1)
                self.assertEqual(evaluation.execution.concurrency, 1)
                path = output_root / uuid4().hex
                agent = path / 'artifacts/harbor/job/trial/agent'; agent.mkdir(parents=True)
                (agent / 'model-usage.json').write_text('{"schema_version":1,"used":1,"requests":[{"id":"call-0","status":"completed","usage":null}]}')
                (agent / 'session.jsonl').write_text('{"type":"message"}\n')
                (agent / 'trajectory.json').write_text('{}')
                private = agent.parent / 'verifier'; private.mkdir(); (private / 'answer.txt').write_text('PRIVATE')
                return {'status': 'completed', 'evaluation_id': path.name, 'errors': {},
                    'metrics': [{'name': 'official_reward', 'value': 0}]}, path
            try:
                with patch('fruitfly_eval.improvement.task_sets.HostConfig.read', return_value=SimpleNamespace(agent_env={'FRUITFLY_MAX_MODEL_CALLS': '2'})), \
                        patch('fruitfly_eval.improvement.task_sets.load_preparation', return_value=prepared):
                    binding = freeze({'id': 'bench', 'source': 'eval', 'request': str(request), 'host': str(host)},
                        context, executor=executor)
                    snapshot = TaskSetSnapshot(binding.entries)
                    evaluator = BatchEvaluator(context, snapshot, (binding,), MultiTaskSettings(), aggregate=assess_batch)
                    result = await evaluator.evaluate(plan, components.snapshot(), EvaluationBatch(snapshot.snapshot_id,
                        tuple(e.key for e in snapshot.entries)))
                self.assertTrue(result.complete)
                self.assertEqual(result.assessment.score, 0)
                self.assertEqual(set(names), {('fixture/a',), ('fixture/b',)})
                self.assertEqual(services.used, {'model': 2, 'execution': 2})
                self.assertTrue(all(b'PRIVATE' not in context.artifacts.read(resource.artifact_id)
                    for trial in result.trials for resource in trial.record.artifacts))
            finally:
                await services.close()
