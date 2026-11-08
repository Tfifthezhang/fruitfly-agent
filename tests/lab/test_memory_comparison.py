"""Memory H is measured through isolated learning without private-answer access."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.improvement.contracts.components import HarnessSnapshot
from fruitfly_agent.improvement.contracts.experiments import EpisodeRequest
from fruitfly_agent.improvement.contracts.execution import ExecutionRecord
from fruitfly_agent.improvement.contracts.plans import RunPlan
from fruitfly_agent.improvement.contracts.tasks import TaskMaterial
from fruitfly_agent.improvement.contracts.versions import SystemVersion, content_hash
from fruitfly_agent.improvement.stages.services import StageServices
from fruitfly_agent.lab.catalog import AssemblyContext, MechanismSelection, ProviderBinding, assemble_lab, builtin_catalog
from fruitfly_agent.lab.improvement.components import component_registry
from fruitfly_agent.lab.context_manager.augmentation.memory.methods.file_memory.trials import MemoryEpisodeExecutor, definition
from tests.support.configuration import component_parameters, with_component_parameters
from tests.support.faux_provider import FauxProvider


class MemoryComparisonTests(unittest.IsolatedAsyncioTestCase):
    def fixture(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        provider = FauxProvider()
        runtime = assemble_lab(AgentLoopConfig(provider), catalog=builtin_catalog(),
            selections=tuple(MechanismSelection(k, parameters={'extract_after_user_chars': 1} if k == 'file-memory' else {})
                for k in ('local-env', 'read-tool', 'file-memory')),
            context=AssemblyContext(root, None, 'fake', lambda *_: ProviderBinding(provider, 'fake', 'offline'),
                model_roles={'executor': 'offline'}))
        self.addCleanup(runtime.config.readable_resources.close)
        registry = component_registry(tuple(v for k, v in runtime.components.items() if k.startswith('text-target:')))
        baseline = registry.snapshot()
        parent = SystemVersion(*(content_hash(v) for v in ('H', 'I', 'S')))
        plan = RunPlan('study', parent, ('file-memory',))
        services = StageServices(plan)
        executions = []
        class Runner:
            async def execute(self, inner_plan, task, harness):
                entries = json.loads(component_parameters(harness.component('memory-library'))['content']['documents'])
                executions.append(entries)
                return ExecutionRecord('exec-' + str(len(executions)), task.task_id, task.material_id,
                    harness.snapshot_id, inner_plan.parent.state, inner_plan.conditions_id, 'completed',
                    entries[0]['body'] if entries else 'empty')
        class Policy:
            def score(self, output, case):
                return SimpleNamespace(score=float(output == case.expected))
        episode = SimpleNamespace(learning_inputs=('My editing preference is tabs.',),
            evaluations=(SimpleNamespace(input='Recall preference', expected='Prefer tabs.'),),
            suite=SimpleNamespace(evaluation_policy=Policy()))
        context = SimpleNamespace(workspace=root, components=registry, component_ids=('file-memory',), plan=plan,
            services=services, runner_factory=lambda *args: Runner(), artifacts=None,
            resource_factories=runtime.components['execution-resources'])
        task = TaskMaterial('adaptation', episode.learning_inputs[0])
        return provider, registry, baseline, context, episode, task

    async def test_candidate_h_prompt_changes_generated_memory_without_private_answer_access(self):
        provider, registry, baseline, context, episode, task = self.fixture()
        executor = MemoryEpisodeExecutor(context, episode, {})
        provider.respond_text('[]')
        before = await executor.run(EpisodeRequest('before', '', baseline, ('memory-library',), task, 0,
            candidate=baseline), signal=context.services.signal)
        document = baseline.component('file-memory')
        values = component_parameters(document)
        values['instructions']['extraction'] = 'CANDIDATE EXTRACTION INSTRUCTIONS'
        modified = with_component_parameters(document, values)
        candidate = HarnessSnapshot(tuple(modified if c.component_id == 'file-memory' else c for c in baseline.components))
        source = 'study-' + content_hash(task.instruction)[7:31]
        provider.respond_text(json.dumps([{'operation': 'add', 'entry': {'kind': 'preference',
            'subject': 'editing', 'description': 'Read for editing preferences.', 'body': 'Prefer tabs.',
            'applicability': 'Editing.', 'supersedes': []}, 'evidence_ids': [source + ':user-1']}]))
        after = await executor.run(EpisodeRequest('after', '', baseline, ('memory-library',), task, 0,
            candidate=candidate), signal=context.services.signal)
        self.assertEqual((0.0,), before.scores_after)
        self.assertEqual((1.0,), after.scores_after)
        self.assertEqual('CANDIDATE EXTRACTION INSTRUCTIONS', provider.calls[-1]['system_prompt'])
        self.assertNotIn('Recall preference', str(provider.calls[-1]['messages']))
        self.assertNotIn('Prefer tabs.', str(provider.calls[-1]['messages']))
        self.assertEqual('[]', registry.adapters['memory-library'].target.retained_documents)
        self.assertEqual({'H'}, set(definition().roles))

    async def test_candidate_threshold_is_executed_and_no_change_needs_no_model(self):
        provider, registry, baseline, context, episode, task = self.fixture()
        original = baseline.component('file-memory')
        values = component_parameters(original)
        values['settings']['extract_after_user_chars'] = 99999
        changed = with_component_parameters(original, values)
        candidate = HarnessSnapshot(tuple(changed if c.component_id == 'file-memory' else c for c in baseline.components))
        result = await MemoryEpisodeExecutor(context, episode, {}).run(
            EpisodeRequest('threshold', '', baseline, ('memory-library',), task, 0, candidate=candidate),
            signal=context.services.signal)
        self.assertEqual((0.0,), result.scores_after)
        self.assertEqual([], provider.calls)
        self.assertEqual('[]', registry.adapters['memory-library'].target.retained_documents)

    async def test_unrelated_or_multiple_components_are_rejected_before_execution(self):
        for ids in ((), ('file-memory', 'memory-library'), ('unregistered-editor',)):
            executor = MemoryEpisodeExecutor(SimpleNamespace(component_ids=ids), None, {})
            with self.subTest(ids=ids), self.assertRaisesRegex(ValueError, 'exactly the File memory H'):
                await executor.run(None, signal=None)

    async def test_registered_material_build_and_independent_verification_use_isolated_learning(self):
        from fruitfly_agent.core.data_model import AssistantMessage, TextBlock
        from fruitfly_agent.core.model_stream import AssistantMessageEventStream, StreamDone
        from fruitfly_agent.improvement.contracts.experiments import ExecutionRequest
        from fruitfly_agent.improvement.contracts.pipeline import ImprovementOutcome
        from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts
        from fruitfly_agent.lab.improvement.tasks import TaskPackCatalog
        from tests.support.task_packs import install, package
        provider, registry, baseline, context, _, _ = self.fixture()
        claims = []
        context.artifacts = MemoryArtifacts()
        context.tasks = TaskPackCatalog(context.workspace)
        context.remaining_verification = None
        context.claim_verification = lambda identity, limit: claims.append((identity, limit))
        for partition in ('development', 'verification'):
            payload = package()
            payload.update(id=partition, compatible_targets=['file-memory'])
            for group in ('train', 'validation', 'holdout'):
                payload[group] = [{'id': group, 'input': partition + '-' + group,
                                  'expected': 'Prefer tabs.'}]
            install(context.workspace, payload)
        directory = context.workspace / '.fruitfly/improvement/experiments/learning'
        directory.mkdir(parents=True)
        (directory / 'experiment.json').write_text(json.dumps({'id': 'learning', 'name': 'Learning comparison',
            'development': ['development'], 'verification': ['verification'], 'max_verifications': 1}))
        def complete(view, **kwargs):
            payload = json.loads(view.messages[0].content)
            changes = []
            if 'CANDIDATE' in view.system_prompt:
                changes = [{'operation': 'add', 'entry': {'kind': 'preference', 'subject': 'editing',
                    'description': 'Read for editing preferences.', 'body': 'Prefer tabs.',
                    'applicability': 'Editing.', 'supersedes': []},
                    'evidence_ids': [payload['evidence'][0]['id']]}]
            async def events():
                yield StreamDone(AssistantMessage([TextBlock(json.dumps(changes))]))
            return AssistantMessageEventStream(events())
        provider.script.extend([complete] * 6)
        execution = definition()
        request = ExecutionRequest('', (), ('file-memory',), 'learning', 'persistent')
        prepared = execution.prepare(context, request)
        ports = execution.build(context, prepared)
        original = baseline.component('file-memory')
        values = component_parameters(original)
        values['instructions']['extraction'] = 'CANDIDATE extraction strategy'
        changed = with_component_parameters(original, values)
        candidate = HarnessSnapshot(tuple(changed if c.component_id == 'file-memory' else c for c in baseline.components))
        try:
            receipt = await ports.runner.execute(context.plan, prepared.task, candidate)
            measurement = await ports.measurements.measure(prepared.task, receipt)
            self.assertEqual(1, measurement.score)
            outcome = ImprovementOutcome(context.plan, prepared.task, receipt, candidate, (), (receipt,), None)
            decision = await ports.verifier.verify(outcome)
            self.assertEqual('verified', decision.assurance)
            self.assertEqual(1, len(claims))
            self.assertIsNotNone(ports.verifier.receipt)
            self.assertEqual(6, len(provider.calls))
            self.assertEqual('[]', registry.adapters['memory-library'].target.retained_documents)
            self.assertEqual(baseline, registry.snapshot())
            for call in provider.calls:
                supplied = str(call['messages'])
                self.assertNotIn('validation', supplied)
                self.assertNotIn('holdout', supplied)
                self.assertNotIn('Prefer tabs.', supplied)
            with self.assertRaisesRegex(ValueError, 'one-use'):
                await ports.verifier.verify(outcome)
        finally:
            await context.services.close()

        # The file-based source uses owner metadata, with no memory branch in the CLI.
        import yaml
        from tests.support.configuration import profile_document
        from tests.support.materials import _write_models
        from fruitfly_agent.experiments.configuration import load_configuration
        from fruitfly_agent.experiments.composition import prepare_experiment
        _write_models(context.workspace)
        config = context.workspace / '.fruitfly/default-config.yaml'
        profile = profile_document(catalog='models.yaml', executor='local', mechanisms=[
            {'id': name} for name in ('local-env', 'read-tool', 'file-memory')])
        config.write_text(yaml.safe_dump({'default_profile': 'baseline', 'profiles': {'baseline': profile}}))
        (config.parent / 'experiment.yaml').write_text(yaml.safe_dump({
            'baseline': {'config': 'default-config.yaml'}, 'tasks': {'inline': {
                'source': 'registered', 'execution': 'memory-learning', 'material': 'learning'}},
            'edit': {'file-memory': {'fields': ['parameters.instructions.extraction']}}}))
        inspected = prepare_experiment(load_configuration(context.workspace), 'improvement', require_credentials=False)
        self.assertEqual('memory-learning', inspected.request.execution_id)
        self.assertEqual(('file-memory',), inspected.request.component_ids)
        self.assertFalse(inspected.summary()['available'], 'materials do not supply a downstream task runner')
