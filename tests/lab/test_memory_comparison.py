"""Memory I candidates are measured through the actual downstream S they create."""
from dataclasses import replace
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
from fruitfly_agent.improvement.workflow.services import WorkflowServices
from fruitfly_agent.lab.catalog import AssemblyContext, MechanismSelection, assemble_lab, builtin_catalog
from fruitfly_agent.lab.improvement.components import component_registry
from fruitfly_agent.lab.context_manager.augmentation.information.file_memory.methods.threshold_maintenance.comparison import MemoryEpisodeExecutor
from tests.support.configuration import component_parameters, with_component_text
from tests.support.faux_provider import FauxProvider


class MemoryComparisonTests(unittest.IsolatedAsyncioTestCase):
    async def test_candidate_prompt_changes_generated_memory_without_private_answer_access(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = FauxProvider()
            runtime = assemble_lab(AgentLoopConfig(provider=provider), catalog=builtin_catalog(),
                selections=tuple(MechanismSelection(k) for k in ('memory-library', 'memory-extractor',
                    'memory-consolidator', 'memory-maintenance')),
                context=AssemblyContext(Path(directory), None, 'fake', lambda *_: self.fail('unexpected model construction')))
            self.addCleanup(runtime.config.readable_resources.close)
            registry = component_registry(tuple(v for k, v in runtime.components.items() if k.startswith('text-target:')))
            baseline = registry.snapshot()
            parent = SystemVersion(*(content_hash(v) for v in ('H', 'I', 'S')))
            plan = RunPlan('study', parent, ('memory-extractor',))
            services = WorkflowServices(plan)
            executions = []
            class Runner:
                async def execute(self, inner_plan, task, harness):
                    document = harness.component('memory-library')
                    entries = json.loads(component_parameters(document)['content']['documents'])
                    executions.append(entries)
                    return ExecutionRecord('exec-' + str(len(executions)), task.task_id, task.material_id,
                        harness.snapshot_id, inner_plan.parent.state, inner_plan.conditions_id, 'completed',
                        entries[0]['body'] if entries else 'empty')
            class Policy:
                def score(self, output, case):
                    return SimpleNamespace(score=float(output == case.expected))
            episode = SimpleNamespace(evaluations=(SimpleNamespace(input='Recall preference', expected='Prefer tabs.'),),
                suite=SimpleNamespace(evaluation_policy=Policy()))
            context = SimpleNamespace(components=registry, editor_config=AgentLoopConfig(provider=provider, model='fake'),
                component_ids=('memory-extractor',), plan=plan, services=services,
                runner_factory=lambda *args: Runner(), artifacts=None)
            task = TaskMaterial('adaptation', 'My editing preference is tabs.')
            executor = MemoryEpisodeExecutor(context, episode, {})
            provider.respond_text('[]')
            before = await executor.run(EpisodeRequest('before', '', baseline, ('memory-library',), task, 0,
                improver=baseline), signal=services.signal)
            candidate = HarnessSnapshot(tuple(with_component_text(c, 'CANDIDATE EXTRACTION INSTRUCTIONS')
                if c.component_id == 'memory-extractor' else c for c in baseline.components))
            source = 'study-' + content_hash(task.instruction)[7:31]
            provider.respond_text(json.dumps([{'operation': 'add', 'entry': {'kind': 'preference',
                'subject': 'editing', 'description': 'Read for editing preferences.', 'body': 'Prefer tabs.',
                'applicability': 'Editing.', 'supersedes': []}, 'evidence_ids': [source + ':user-1']}]))
            after = await executor.run(EpisodeRequest('after', '', baseline, ('memory-library',), task, 0,
                improver=candidate), signal=services.signal)
            self.assertEqual((0.0,), before.scores_after)
            self.assertEqual((1.0,), after.scores_after)
            self.assertEqual('CANDIDATE EXTRACTION INSTRUCTIONS', provider.calls[-1]['system_prompt'])
            self.assertNotIn('Recall preference', str(provider.calls[-1]['messages']))
            self.assertEqual('[]', registry.adapters['memory-library'].target.retained_documents)

    async def test_multiple_editor_operations_are_rejected_before_any_execution(self):
        from types import SimpleNamespace
        from fruitfly_agent.lab.context_manager.augmentation.information.file_memory.methods.threshold_maintenance.comparison import MemoryEpisodeExecutor
        for ids in ((), ('memory-extractor', 'memory-consolidator'), ('unregistered-editor',)):
            executor = MemoryEpisodeExecutor(SimpleNamespace(component_ids=ids), None, {})
            with self.subTest(ids=ids), self.assertRaisesRegex(ValueError, 'exactly one editor operation'):
                await executor.run(None, signal=None)
