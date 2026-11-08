"""Propose once from a synthetic retained record; no task or model is executed."""
import asyncio
from dataclasses import replace
import tempfile

from fruitfly_agent.improvement.contracts.optimization import OptimizationSpec
from fruitfly_agent.improvement.contracts.plans import RunPlan
from fruitfly_agent.improvement.contracts.tasks import TaskMaterial
from fruitfly_agent.improvement.contracts.components import ComponentDocument, ComponentFile, HarnessSnapshot
from fruitfly_agent.improvement.contracts.candidates import CandidateBundle, EditReason
from fruitfly_agent.improvement.contracts.editing import ProposalResult
from fruitfly_agent.improvement.contracts.execution import ExecutionRecord
from fruitfly_agent.improvement.contracts.research import ResearchBatch
from fruitfly_agent.improvement.contracts.stages import StageInputs
from fruitfly_agent.improvement.contracts.versions import SystemVersion, content_hash
from fruitfly_agent.lab.improvement.components import ComponentRegistry, FileComponentAdapter
from fruitfly_agent.lab.improvement.editor.generators import GeneratorRegistry
from fruitfly_agent.lab.improvement.editor.proposal import ProposalStage
from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts
from fruitfly_agent.run.improvement.service import ResearchService


class Rule:
    generator_id = 'example-rule'
    required_capabilities = frozenset()
    supports_task_sets = True

    async def propose(self, request, services):
        component = replace(request.baseline.components[0], files=(ComponentFile(
            'instructions.txt', 'Check the deliverable before returning it.'),))
        candidate = CandidateBundle(request.plan.parent, request.baseline,
            HarnessSnapshot((component,)), self.generator_id,
            (EditReason(component.component_id, 'Synthetic fixture omits a final check.',
                (request.records[0].run_id,), expected_effect='The candidate explicitly requests a deliverable check.'),))
        return ProposalResult((candidate,))


async def main():
    document = ComponentDocument('prompt', 'system-prompt', 'H', 'text-v1',
        (ComponentFile('instructions.txt', 'Complete the task.'),))
    components = ComponentRegistry((FileComponentAdapter(document, lambda value: None,
        optimization=OptimizationSpec('H', 'documents')),))
    generators = GeneratorRegistry(); generators.register('example-rule', Rule)
    plan = RunPlan('offline', SystemVersion(*(content_hash(v) for v in ('H', 'I', 'S'))),
        ('prompt',), generator_id='example-rule')
    baseline = components.snapshot()
    task = TaskMaterial('task', 'Create a deliverable.')
    # This is explicitly authored synthetic material, not a measured baseline.
    record = ExecutionRecord('synthetic-reference', task.task_id, task.material_id,
        baseline.snapshot_id, plan.parent.state, plan.conditions_id, 'completed',
        'Synthetic fixture output without a final check.', model_calls=0)
    with tempfile.TemporaryDirectory() as directory:
        service = ResearchService(directory, 'offline', MemoryArtifacts(), plan=plan,
            proposal=ProposalStage(generators=generators, components=components))
        service.revise({'fixture': 'synthetic retained observations'})
        batch = service.put('batch.json', ResearchBatch((task,), (record,)).to_dict())
        harness = service.put('harness.json', baseline.to_dict())
        result = await service.perform_named('propose', StageInputs(harness=harness, batches=(batch,)))
        candidate = CandidateBundle.from_dict(service.read(result.outputs[0])['candidates'][0])
        print(candidate.harness.components[0].files[0].text)
        print('Synthetic proposal only; no quality or activation claim.')


if __name__ == '__main__':
    asyncio.run(main())
