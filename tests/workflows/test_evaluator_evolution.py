"""Evaluator candidates affect inner choices but never their own acceptance proof."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import yaml

from fruitfly_agent.core.model_stream import AssistantMessageEventStream
from fruitfly_agent.interactive import AgentApplication
from fruitfly_agent.improvement.contracts.candidates import CandidateBundle, EditReason
from fruitfly_agent.improvement.contracts.components import ComponentFile, HarnessSnapshot
from fruitfly_agent.improvement.contracts.editing import ProposalResult
from fruitfly_agent.lab.improvement.editor.generators import GeneratorRegistry
from fruitfly_agent.run import RunApplicationFactory
from tests.support.self_improver import experiment_factory, ProceduralProvider
from tests.support.model_evaluation import judgment


class EvaluatorRule:
    generator_id = 'self-rule'
    required_capabilities = frozenset()

    async def propose(self, request, services):
        document = request.baseline.component('improvement-evaluator')
        value = json.loads(document.files[0].text)
        value['instructions']['compare'] = 'PREFER_VERIFIED_OUTPUT: inspect completed task outputs.'
        changed = replace(document, files=(ComponentFile('instructions.txt', json.dumps(value, indent=2)),))
        harness = HarnessSnapshot(tuple(changed if c.component_id == changed.component_id else c for c in request.baseline.components))
        return ProposalResult((CandidateBundle(request.plan.parent, request.baseline, harness, self.generator_id,
            (EditReason(changed.component_id, 'Synthetic downstream choice contrast.', (request.records[0].run_id,), expected_effect='The proposed behavior appears in the subsequent execution.'),)),))


class EvaluatorEvolutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_fixed_evaluator_trials_require_private_gain_and_restore_exact_activated_bytes(self):
        original = ProceduralProvider.reply
        def response(provider, view, *, signal=None):
            if 'Evaluate granted evidence' in view.system_prompt:
                value = judgment(view, choice=1 if 'PREFER_VERIFIED_OUTPUT' in view.system_prompt else 0)
                return AssistantMessageEventStream(provider._message_stream(value))
            return original(provider, view, signal=signal)
        with tempfile.TemporaryDirectory() as directory, patch.object(ProceduralProvider, 'reply', response):
            root = Path(directory)
            factory, provider, request = experiment_factory(root)
            path = root / '.fruitfly/config.yaml'
            document = yaml.safe_load(path.read_text())
            profile = document['profiles'][document['default_profile']]
            profile['I']['improvement-editor'] = {'inline': {
                'id': 'improvement-editor', 'role': 'I', 'implementation': 'improvement-editor',
                'parameters': {'instructions': {'invariant': 'STEP STEP: propose an observed procedure fix.'}}}}
            path.write_text(yaml.safe_dump(document))
            factory.reload_configuration()
            generators = GeneratorRegistry(); generators.register('self-rule', EvaluatorRule)
            factory._component_jobs.generators = generators
            factory.improvement_bindings = replace(factory.improvement_bindings, generators=generators)
            request = replace(request, component_ids=('improvement-evaluator',))
            app = AgentApplication(factory)
            await app.start()
            try:
                before = factory.system_version()
                results = await app.improve('', preview_token=app.workflow_preview(request).preview_token)
                self.assertTrue(results)
                outcome = factory._component_jobs.outcome
                self.assertEqual('verified', outcome.decision.assurance)
                self.assertEqual(before, factory.system_version())
                stored = outcome.harness.component('improvement-evaluator').files[0].text
                self.assertIn('\n', stored)
                await app.adopt_candidate(results[0].candidate_id)
                self.assertNotEqual(before.improver, factory.system_version().improver)
                self.assertTrue(any('PREFER_VERIFIED_OUTPUT' in call['system_prompt'] for call in provider.calls))
                self.assertTrue(any('independent' in repr(call['messages']) for call in provider.calls))
            finally:
                await app.close()
            fresh = RunApplicationFactory(cwd=root, environment={}, provider_registry=factory.provider_registry,
                improvement_bindings=factory.improvement_bindings)
            recovered = AgentApplication(fresh)
            await recovered.start()
            try:
                self.assertEqual(stored, fresh._current_targets['improvement-evaluator'].snapshot().text)
                self.assertEqual('adopted', fresh.candidate_store.read(results[0].candidate_id).status)
            finally:
                await recovered.close()
