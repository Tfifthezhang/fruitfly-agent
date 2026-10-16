"""Pinned original task command and normal Application entry without Docker or models."""
import asyncio
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from eval.benchmarks.base import PreflightResult
from eval.benchmarks.terminal_bench import TerminalBenchAdapter
from eval.evidence import material_hash
from eval.trial import run_trial
from fruitfly_agent.lab.improvement.experiments import TaskReference
from tests.support.harbor import load_harbor_agent


class OriginalTaskExecutorTests(unittest.TestCase):
    def task(self, root):
        task = root/'task'
        (task/'tests').mkdir(parents=True)
        (task/'instruction.md').write_text('Complete the original task')
        (task/'task.toml').write_text('[environment]\ncpus = 1\n')
        (task/'tests/test.sh').write_text('exit 0\n')
        return task, TaskReference('terminal-bench@2.0','task','revision',material_hash(task),
            'Complete the original task','official','cpu')

    def test_executor_uses_original_path_one_attempt_and_owned_packet(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()
            task,ref=self.task(root)
            adapter=TerminalBenchAdapter()
            output=root/'new-output'
            packet={'lease_id':'one','instruction':ref.instruction}
            request={'schema_version':1,'runtime':{'config_path':str(root/'config'),'profile':'default','working_directory':str(root)},
                'benchmark_id':'terminal-bench','task':ref.to_dict(),'task_path':str(task),
                'source_root':str(Path(__file__).resolve().parents[2]),'packet':packet,'timeout_seconds':30}
            commands=[]
            def run(command, **kwargs):
                commands.append(command)
                trial=output/'trial/task__1'
                trial.mkdir(parents=True)
                (trial/'result.json').write_text(json.dumps({'task_name':'task','config':{'task':{}},
                    'verifier_result':{'rewards':{'reward':0}}}))
                return 0,''
            with patch('eval.trial.builtin_catalog',return_value=SimpleNamespace(get=lambda _:adapter)), patch.object(
                adapter,'preflight',return_value=PreflightResult(True,(),('harbor',))), patch(
                'eval.trial._runtime_files',return_value=(root/'config',root/'models',())), patch('eval.trial._run_harbor_job',side_effect=run):
                result=run_trial(request,output_root=output)
            command=commands[0]
            self.assertNotIn('--dataset',command)
            self.assertEqual(command[command.index('--path')+1],str(task))
            self.assertEqual(command[command.index('--n-tasks')+1],'1')
            self.assertIn('trial_request_path='+str(output/'trial-request.json'),command)
            self.assertEqual(result['evidence']['task'],ref.to_dict())
            self.assertEqual(result['evidence']['score'],0)

    def test_changed_task_fails_before_preflight(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();task,ref=self.task(root)
            (task/'tests/test.sh').write_text('changed verifier')
            request={'schema_version':1,'runtime':{'config_path':'config','profile':'default','working_directory':str(root)},
                'benchmark_id':'terminal-bench','task':ref.to_dict(),'task_path':str(task),
                'source_root':'unused','packet':{},'timeout_seconds':30}
            with patch('eval.trial.builtin_catalog') as catalog:
                with self.assertRaisesRegex(ValueError,'material changed'):
                    run_trial(request,output_root=root/'new')
                catalog.assert_not_called()

    def test_installed_bridge_preserves_allocation_and_effective_instruction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            agent=load_harbor_agent().__new__(load_harbor_agent())
            agent.profile='default'
            agent.trial_request_path=root/'request.json'
            agent.trial_request_path.write_text(json.dumps({'lease_id':'fixed','instruction':'raw'}))
            agent.exec_as_agent=AsyncMock()
            captured=[]
            async def upload(path,destination):
                captured.append(json.loads(path.read_text()))
            environment=SimpleNamespace(upload_file=AsyncMock(side_effect=upload))
            asyncio.run(agent.run('Complete effective task',environment,SimpleNamespace(metadata=None)))
            self.assertEqual(captured,[{'lease_id':'fixed','instruction':'Complete effective task'}])
            command=agent.exec_as_agent.call_args.kwargs['command']
            self.assertIn('-m fruitfly_agent.run.trial',command)
            self.assertIn('--source /installed-agent/fruitfly/source',command)
