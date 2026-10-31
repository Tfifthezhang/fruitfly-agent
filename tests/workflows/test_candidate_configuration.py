"""A component candidate changes actual file execution and exports an ordinary config."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

import yaml

from fruitfly_agent.experiments.scaffolding import initialize_workspace
from fruitfly_agent.interactive import AgentApplication
from fruitfly_agent.interactive.contracts.improvement import WorkflowRequest
from fruitfly_agent.lab.catalog import load_system_config
from fruitfly_agent.lab.improvement.api import WorkflowBindings
from fruitfly_agent.lab.improvement.editor.generators import GeneratorRegistry
from fruitfly_agent.improvement.contracts.candidates import CandidateBundle, EditReason
from fruitfly_agent.improvement.contracts.components import HarnessSnapshot, ComponentFile
from fruitfly_agent.improvement.contracts.editing import ProposalResult
from fruitfly_agent.improvement.contracts.assessment import Measurement
from fruitfly_agent.improvement.execution.facts import read_facts
from fruitfly_agent.run import RunApplicationFactory
from tests.support.model_evaluation import RoleProvider as FauxProvider


class CandidateConfigurationTests(unittest.IsolatedAsyncioTestCase):
    async def test_candidate_parallelism_and_exported_config_match_without_changing_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initialize_workspace(root)
            execution = root / '.fruitfly/components/H/execution-policy.yaml'
            value = yaml.safe_load(execution.read_text())
            value['parameters']['settings']['tool_execution']['max_parallel'] = 1
            execution.write_text(yaml.safe_dump(value))
            original = execution.read_bytes()
            provider = FauxProvider()
            for _ in range(2):
                for name in ('a','b'):provider.respond_tool_call('write',{'path':name,'content':name})
                provider.respond_text('done')
            providers = Mock(); providers.create.return_value = provider
            class Generator:
                generator_id = 'limit-rule'
                required_capabilities = frozenset()
                async def propose(self, request, services):
                    old = request.baseline.component('execution-policy')
                    value = json.loads(old.files[0].text)
                    value['settings']['tool_execution']['max_parallel'] = 2
                    changed = replace(old, files=(ComponentFile('instructions.txt', json.dumps(value)),))
                    harness = HarnessSnapshot(tuple(changed if d.component_id == changed.component_id else d
                                                    for d in request.baseline.components))
                    return ProposalResult((CandidateBundle(request.plan.parent, request.baseline, harness, self.generator_id,
                        (EditReason(changed.component_id, 'Compare actual tool execution.', (request.records[0].run_id,), expected_effect='The proposed behavior appears in the subsequent execution.'),)),))
            class Measurements:
                async def measure(self, task, record):
                    facts = read_facts(record, Artifacts())
                    reference=next(r.artifact_id for r in record.artifacts if r.path=='runtime-execution.json')
                    return Measurement(record.run_id,'parallelism-fixture',json.loads(Artifacts().read(reference))['tool_execution']['max_parallel'])
            # The scorer reads only the public artifact interface provided by the host.
            class Artifacts:
                def read(self, reference):
                    return factory.artifact_store.read_bytes(reference)
            generators = GeneratorRegistry(); generators.register('limit-rule', Generator)
            factory = RunApplicationFactory(cwd=root, config_path=str(root / '.fruitfly/default-config.yaml'),
                environment={}, provider_registry=providers,
                improvement_bindings=WorkflowBindings(generators=generators, measurements=Measurements(),
                    component_options={'execution-policy': {'editable_fields': ['parameters.settings.tool_execution.max_parallel'],
                        'bounds': {'parameters.settings.tool_execution.max_parallel': {'minimum': 1, 'maximum': 2}}}}))
            app = AgentApplication(factory)
            await app.start()
            try:
                request = WorkflowRequest('Write a and b.', component_ids=('execution-policy',), generator_id='limit-rule',
                    strategy_id='simple', depth=1, verification='scored', retain_experience=False)
                preview = app.workflow_preview(request)
                await app.improve('', preview_token=preview.preview_token)
                candidates = list((root / '.fruitfly/improvement/jobs').glob('*/candidates/*/config.yaml'))
                self.assertEqual(len(candidates), 1)
                selected = load_system_config(candidates[0]).select()
                self.assertEqual(selected.execution['tool_execution']['max_parallel'], 2)
                result = json.loads(next((root / '.fruitfly/improvement/jobs').glob('*/result.json')).read_text())
                self.assertEqual([record['model_calls'] for record in result['records']], [3, 3])
                self.assertEqual(execution.read_bytes(), original)
                self.assertEqual(app.runtime_manifest['execution']['tool_execution']['max_parallel'], 1)
            finally:
                await app.close()
