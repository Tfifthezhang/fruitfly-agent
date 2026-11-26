"""Real Harbor/WorkBuddy contracts without Docker, downloads or model requests."""
import asyncio
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class WorkBuddyContractTests(unittest.TestCase):
    def test_official_bridge_job_schema_and_named_source_metrics(self):
        from harbor.models.job.config import JobConfig
        from harbor.job import Job
        from harbor.agents.installed.base import BaseInstalledAgent
        from fruitfly_eval.workbuddy.worker import describe
        from fruitfly_eval.workbuddy.agent import WorkBuddyFruitFlyAgent
        from fruitfly_eval.workbuddy.runner import job_configuration
        from fruitfly_eval.runtime import prepare_runtime
        from fruitfly_eval.contracts import EvaluationRequest
        from tests.support.workbuddy import fixture
        checkout = Path(os.environ['FRUITFLY_WORKBUDDY_CHECKOUT']).resolve()
        state = describe(checkout)
        self.assertEqual(state['engine']['harbor'], '0.23.0')
        self.assertTrue(issubclass(WorkBuddyFruitFlyAgent, BaseInstalledAgent))
        self.assertFalse(WorkBuddyFruitFlyAgent.__abstractmethods__)
        from workbuddy_bench.judge import CompositeVerifier
        from fruitfly_eval.workbuddy.environment import PreparedWorkBuddyEnvironment
        from harbor.environments.docker.docker import DockerEnvironment
        self.assertTrue(issubclass(PreparedWorkBuddyEnvironment, DockerEnvironment))
        self.assertTrue(callable(CompositeVerifier))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            host = fixture(root)
            output = root / 'runtime-output'; output.mkdir()
            config, models, secrets = prepare_runtime(runtime={'working_directory': str(root)},
                output_dir=output, environment={'EXPERIMENT_TEST_KEY': 'offline-fixture'}, model_relay=True)
            runtime = json.loads((output / 'runtime.json').read_text())
            receipt = {'dataset': 'wb-bench-code-v1.0', 'bench': {'environment': {}},
                'runtime': {'source': str(root), 'mounts': []},
                'tasks': [{'path': str(host.task_directory / 'tasks/first')}]}
            request = EvaluationRequest.from_dict({'runtime': {'working_directory': str(root)},
                'benchmark': {'id': 'workbuddy-code', 'variant': 'full'}})
            for relay in (False, True):
                # Schema admission is platform-independent; select the native
                # Linux transport without starting a Linux container here.
                with patch('fruitfly_eval.bridges.model_access.platform.system', return_value='Linux'):
                    job = job_configuration(request, host, receipt, root=output, config=config, models=models,
                        profile=runtime['profile'], secrets=secrets, relay_directory=root / 'relay', relay_required=relay)
                parsed = JobConfig.model_validate(job)
                self.assertTrue(all(m.get('read_only', True) for m in job['environment']['mounts']))
                engine = asyncio.run(Job.create(parsed))
                self.assertEqual(len(engine), 1)
                # Check the SDK's resolved integration state: a source introduced
                # by explicit local tasks must have an actual numerical metric.
                metrics = engine._metrics[receipt['dataset']]
                self.assertTrue(metrics)
                self.assertEqual(metrics[0].compute([{'reward': 1.0}])['mean'], 1.0)
                self.assertIs(engine.on_trial_started(lambda event: None), engine)
