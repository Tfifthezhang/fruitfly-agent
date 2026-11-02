"""Layered compaction candidates alter isolated execution, activation and recovery."""
import json
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from fruitfly_agent.core.data_model import AssistantMessage, TextBlock, ToolCallBlock, CustomMessage
from fruitfly_agent.core.model_stream import AssistantMessageEventStream, StreamDone
from fruitfly_agent.interactive import AgentApplication
from fruitfly_agent.interactive.contracts.improvement import WorkflowRequest
from fruitfly_agent.lab.improvement.api import WorkflowBindings
from fruitfly_agent.lab.improvement.editor.generators import GeneratorRegistry
from fruitfly_agent.improvement.contracts.candidates import CandidateBundle, EditReason
from fruitfly_agent.improvement.contracts.components import HarnessSnapshot, ComponentFile
from fruitfly_agent.improvement.contracts.editing import ProposalResult
from tests.support.task_execution import TaskApplicationFixture as RunApplicationFactory
from tests.support.improvers import FirstSelector, SyntheticVerification
from tests.support.materials import _write_models
from tests.support.faux_provider import FauxProvider
from tests.support.compaction import structured_summary


class CompactionProvider(FauxProvider):
    def __call__(self, view, *, signal=None):
        self.script.append(self.reply)
        return super().__call__(view, signal=signal)

    def reply(self, view, *, signal=None):
        if view.system_prompt == 'Summarize archived task evidence.':
            text = structured_summary('OPTIMIZED' if 'OPTIMIZED' in str(view.messages[0].content) else 'baseline')
            value = AssistantMessage([TextBlock(text)], stop_reason='stop')
        elif 'Evaluate granted evidence' in view.system_prompt:
            from tests.support.model_evaluation import judgment, payload
            value = judgment(view, choice=len(payload(view)['executions'])-1)
        elif any(isinstance(m, CustomMessage) for m in view.messages):
            memory = '\n'.join(m.text for m in view.messages if isinstance(m, CustomMessage))
            value = AssistantMessage([TextBlock('A' if 'OPTIMIZED' in memory else 'wrong')], stop_reason='stop')
        else:
            value = AssistantMessage([ToolCallBlock('read-input-' + str(len(self.calls)), 'read', {'path':'input.txt'})], stop_reason='toolUse')
        return AssistantMessageEventStream(self._message_stream(value))


class CompactionGenerator:
    generator_id = 'compaction-test'
    required_capabilities = frozenset()
    async def propose(self, request, services):
        source = request.baseline.component('layered-compaction')
        value = json.loads(source.files[0].text)
        mode = value['settings']['mode']
        value['instructions']['summary' if mode == 'hybrid' else 'readback'] += ' OPTIMIZED'
        updated = replace(source, files=(ComponentFile('instructions.txt', json.dumps(value)),))
        harness = HarnessSnapshot(tuple(updated if c.component_id == source.component_id else c for c in request.baseline.components))
        return ProposalResult((CandidateBundle(request.plan.parent, request.baseline, harness, self.generator_id,
            (EditReason(source.component_id, 'Synthetic compaction behavior.', (request.records[0].run_id,),
                expected_effect='Provider-visible compaction includes the synthetic marker.'),)),))


class LayeredCompactionImprovementTests(unittest.IsolatedAsyncioTestCase):
    async def test_deterministic_and_hybrid_candidates_activate_and_recover(self):
        for mode in ('deterministic', 'hybrid'):
            with self.subTest(mode=mode):
                await self.exercise(mode)

    async def exercise(self, mode):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_models(root)
            (root/'input.txt').write_text(('original evidence line\n'*700))
            provider = CompactionProvider()
            providers = Mock(); providers.create.return_value = provider
            generators = GeneratorRegistry(); generators.register(CompactionGenerator.generator_id, CompactionGenerator)
            factory = RunApplicationFactory(cwd=root, environment={}, provider_registry=providers,
                improvement_bindings=WorkflowBindings(generators=generators, selector=lambda *args:FirstSelector(),
                    verifier=SyntheticVerification()))
            factory.configuration.set_mechanism('layered-compaction', enabled=True)
            factory.configuration.set_parameter('layered-compaction', 'keep_recent_groups', '1')
            factory.configuration.set_parameter('layered-compaction', 'tail_tokens', '256')
            if mode == 'hybrid':
                factory.configuration.set_parameter('layered-compaction', 'summary_model_profile', 'local')
                factory.configuration.set_parameter('layered-compaction', 'mode', 'hybrid')
            factory.configuration.save(); factory.reload_configuration()
            app = AgentApplication(factory); await app.start()
            try:
                # A small fixed context exercises actual reduction after the read result.
                config = factory._current_runtime_config
                factory._current_runtime_config = replace(config, context_window=5000, max_tokens=128)
                await app.submit('DAILY_ONLY: Read input.txt, then answer.')
                version = factory.system_version()
                for generation in range(1):
                    request = WorkflowRequest('Read input.txt, then answer.', ('input.txt',), ('layered-compaction',),
                        generator_id=CompactionGenerator.generator_id, scope='persistent')
                    preview = app.workflow_preview(request)
                    candidates = await app.improve('', preview_token=preview.preview_token)
                    outcome = factory._component_jobs.outcome
                    self.assertEqual(len(candidates), 1, outcome.stop_reason)
                    self.assertEqual(len(outcome.records), 2)
                    self.assertEqual(outcome.selected.output, 'A')
                    for receipt in outcome.records:
                        references={resource.path:resource.artifact_id for resource in receipt.artifacts}
                        self.assertIn('projection.json',references)
                        self.assertIn('layered_compaction/checkpoints.json',references)
                        self.assertIn('original evidence line',factory.artifact_store.read_text(references['trajectory.json']))
                        self.assertNotIn('DAILY_ONLY',factory.artifact_store.read_text(references['trajectory.json']))
                        self.assertIn('History index:',factory.artifact_store.read_text(references['projection.json']))
                        self.assertTrue(json.loads(factory.artifact_store.read_text(references['layered_compaction/checkpoints.json'])))
                        self.assertTrue(any(name.startswith('layered_compaction/') and name.endswith('.txt') for name in references))
                    self.assertEqual(factory.system_version(), version)
                    await app.adopt_candidate(candidates[0].candidate_id)
                    adopted = factory.system_version()
                    self.assertNotEqual(adopted.harness, version.harness)
                    self.assertEqual(adopted.improver, version.improver)
                    version = adopted
                    factory._current_runtime_config = replace(factory._current_runtime_config, context_window=5000, max_tokens=128)
                self.assertEqual((root/'input.txt').read_text(), 'original evidence line\n'*700)
                auxiliary = [call for call in provider.calls if call['system_prompt']=='Summarize archived task evidence.']
                if mode == 'hybrid':
                    self.assertTrue(auxiliary)
                    self.assertTrue(any('OPTIMIZED' in str(c['messages'][0].content) for c in auxiliary))
                else:
                    self.assertEqual(auxiliary, [])
                task_calls = [c for c in provider.calls if any(isinstance(m,CustomMessage) for m in c['messages'])]
                self.assertTrue(task_calls)
                self.assertTrue(all(set(c['tools']) == {'read','write','edit','bash'} for c in task_calls))
                await app.submit('Read input.txt, then answer.')
                session = Path(app.status.session_path)
            finally:
                await app.close()
            await app.start(resume=True, session_path=session)
            try:
                self.assertEqual(factory.system_version(), version)
            finally:
                await app.close()
