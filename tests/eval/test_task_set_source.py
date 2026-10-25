"""Benchmark collections pass single selected tasks through existing Eval lifecycle."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

import yaml
from eval.improvement.task_sets import freeze
from fruitfly_agent.lab.improvement.api import (TaskSetSnapshot, MultiTaskSettings, BatchEvaluator,
    ExecutionContext, WorkflowServices, RunPlan, EvaluationBatch, ComponentRegistry, TextComponentAdapter)
from fruitfly_agent.lab.base_prompt.target import BasePromptTarget
from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts
from fruitfly_agent.lab.improvement.assessment.joint import assess_batch
from tests.support.pipeline import version


class EvalCollectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_many_prepared_tasks_remain_individual_executions_with_private_grading_excluded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / '.fruitfly'; state.mkdir()
            config = state / 'default-config.yaml'
            config.write_text(yaml.safe_dump({'schema_version': 1, 'default_profile': 'baseline', 'profiles': {'baseline': {
                'model': {'catalog': 'models.yaml', 'profile': 'fake'}}}}))
            (state / 'models.yaml').write_text('models: {}\n')
            request = root / 'request.json'
            request.write_text(json.dumps({'schema_version': 2, 'runtime': {'working_directory': str(root)},
                'benchmark': {'id': 'terminal-bench-4', 'variant': 'full'}}))
            host = root / 'host.yaml'; host.write_text('fixture host')
            tasks = []
            for name in ('a', 'b'):
                path = root / name; path.mkdir(); (path / 'instruction.md').write_text('Complete fixture ' + name)
                tasks.append({'id': 'fixture/' + name, 'path': str(path)})
            source = Path(__file__).resolve().parents[2]
            files = [(name, hashlib.sha256((source / name).read_bytes()).hexdigest()) for name in (
                'fruitfly_agent/run/runtime/limits.py', 'fruitfly_agent/run/cli.py', 'eval/harbor_agent.py',
                'fruitfly_agent/core/loop.py', 'fruitfly_agent/run/configuration/profile.py',
                'fruitfly_agent/run/runtime/assembly.py', 'fruitfly_agent/runtime_spec/execution.py',
             'fruitfly_agent/runtime_spec/profiles.py', 'fruitfly_agent/runtime_spec/selections.py', 'eval/runtime.py')]
            prepared = {'id': 'prepared-fixture', 'tasks': tasks, 'runtime': {'installation': {'files': files}}}
            components = ComponentRegistry((TextComponentAdapter(BasePromptTarget('baseline'), 'system-prompt'),))
            plan = RunPlan('joint-eval', version(), ('base_prompt',), feedback='scored', max_model_calls=20)
            services = WorkflowServices(plan)
            context = ExecutionContext(root, MemoryArtifacts(), components, None, None, None, plan=plan, services=services)
            context.runtime_config, context.runtime_profile = config, None
            names = []
            async def executor(evaluation, host_path, *, directory, output_root, emit):
                names.append(evaluation.benchmark.task_names)
                self.assertEqual(len(names[-1]), 1)
                self.assertEqual(evaluation.execution.concurrency, 1)
                path = output_root / uuid4().hex
                agent = path / 'artifacts/harbor/job/trial/agent'; agent.mkdir(parents=True)
                (agent / 'model-budget.json').write_text('{"schema_version":1,"limit":2,"used":1}')
                (agent / 'session.jsonl').write_text('{"type":"message"}\n')
                (agent / 'trajectory.json').write_text('{}')
                private = agent.parent / 'verifier'; private.mkdir(); (private / 'answer.txt').write_text('PRIVATE')
                return {'status': 'completed', 'evaluation_id': path.name, 'errors': {},
                    'metrics': [{'name': 'official_reward', 'value': 0}]}, path
            try:
                with patch('eval.improvement.task_sets.HostConfig.read', return_value=SimpleNamespace(agent_env={'FRUITFLY_MAX_MODEL_CALLS': '2'})), \
                        patch('eval.improvement.task_sets.load_preparation', return_value=prepared):
                    binding = freeze({'id': 'bench', 'source': 'eval', 'request': str(request), 'host': str(host), 'model_calls': 2},
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
