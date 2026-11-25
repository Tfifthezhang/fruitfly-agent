"""Benchmark execution preserves ordinary API and subscription connection identity."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
import yaml

from fruitfly_eval.contracts import EvaluationRequest
from fruitfly_eval.runtime import prepare_runtime
from fruitfly_eval.workbuddy.runner import job_configuration
from fruitfly_agent.providers.connections.methods.opencode_go.requests import GoRequests
from tests.support.workbuddy import fixture


class WorkBuddyModelTests(unittest.TestCase):
    def test_same_benchmark_accepts_api_and_go_without_a_generic_model_translation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            host = fixture(root)
            host = replace(host, model_relay={'network_url': 'https://relay.example', 'listen_host': '0.0.0.0',
                'certificate': '/fixture/server.pem', 'private_key': '/fixture/key.pem', 'ca': '/fixture/ca.pem'})
            request = EvaluationRequest.from_dict({'runtime': {'working_directory': str(root)},
                'benchmark': {'id': 'workbuddy-code', 'variant': 'smoke'}})
            receipt = {'bench': {'environment': {}}, 'dataset': 'wb-bench-code-v1.0',
                'tasks': [{'path': '/frozen/task'}], 'runtime': {'source': '/frozen/source', 'mounts': []}}
            system_path = root / '.fruitfly/default-config.yaml'
            system = yaml.safe_load(system_path.read_text())
            go = {'connections': {'personal': {'integration': 'opencode-go', 'credential': {'env': 'GO_FIXTURE_KEY'}}},
                  'models': {'go': {'connection': 'personal', 'model': 'offline-go-fixture',
                      'context_window': 16000, 'max_output_tokens': 1024,
                      'capabilities': {'tools': True, 'streaming': True, 'vision': False, 'reasoning': False}}}}
            (root / '.fruitfly/subscriptions.yaml').write_text(yaml.safe_dump(go))
            for mode in ('api', 'go'):
                profile = system['profiles']['baseline']
                if mode == 'go':
                    profile['models']['subscriptions'] = 'subscriptions.yaml'
                    profile['models']['roles']['executor'] = 'go'
                system_path.write_text(yaml.safe_dump(system))
                output = root / mode; output.mkdir()
                config, models, secrets = prepare_runtime(runtime={'working_directory': str(root)},
                    output_dir=output, environment={'EXPERIMENT_TEST_KEY': 'PRIVATE_FIXTURE'}, model_relay=True)
                runtime = json.loads((output / 'runtime.json').read_text())
                job = job_configuration(request, host, receipt, root=output, config=config, models=models,
                    profile=runtime['profile'], secrets=secrets, relay_directory=root / 'relay',
                    relay_required=bool(runtime['connected_models']))
                self.assertNotIn('PRIVATE_FIXTURE', json.dumps(job))
                if mode == 'go':
                    values = yaml.safe_load(models.read_text())['models']['go']
                    self.assertEqual(values['access']['integration'], 'opencode-go')
                    self.assertEqual(values['model'], 'offline-go-fixture')
                    self.assertIn('model_relay_directory', job['agents'][0]['kwargs'])
                    self.assertIn('relay.example', job['agents'][0]['extra_allowed_hosts'])
                    self.assertNotIn('GO_FIXTURE_KEY', secrets)
                    headers = GoRequests().prepare({}, 'independent-trial')['extra_headers']
                    self.assertEqual(headers['x-opencode-session'], 'independent-trial')
                    self.assertEqual(headers['User-Agent'], 'fruitfly-agent/0.1')
                else:
                    self.assertEqual(runtime['connected_models'], [])
                    self.assertNotIn('model_relay_directory', job['agents'][0]['kwargs'])
