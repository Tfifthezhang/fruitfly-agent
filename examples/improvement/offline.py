"""Run the public workflow with a deterministic generator and synthetic execution."""
from fruitfly_agent.improvement.contracts.optimization import OptimizationSpec
import asyncio
from dataclasses import replace
from uuid import uuid4

from fruitfly_agent.improvement.contracts.plans import RunPlan
from fruitfly_agent.improvement.contracts.tasks import TaskMaterial
from fruitfly_agent.improvement.contracts.components import ComponentDocument, ComponentFile, HarnessSnapshot
from fruitfly_agent.improvement.contracts.candidates import CandidateBundle, EditReason
from fruitfly_agent.improvement.contracts.editing import ProposalResult
from fruitfly_agent.lab.improvement.components import ComponentRegistry, FileComponentAdapter
from fruitfly_agent.lab.improvement.editor.generators import GeneratorRegistry
from fruitfly_agent.improvement.workflow.services import WorkflowServices
from fruitfly_agent.lab.improvement.workflow import ImprovementWorkflow as ComponentWorkflow
from fruitfly_agent.improvement.contracts.execution import ExecutionRecord
from fruitfly_agent.improvement.contracts.assessment import SelectionDecision
from fruitfly_agent.improvement.contracts.versions import SystemVersion, content_hash


class Rule:
    generator_id = 'example-rule'
    required_capabilities = frozenset()

    async def propose(self, request, services):
        component = replace(request.baseline.components[0],
            files=(ComponentFile('instructions.txt', 'Check the deliverable before returning it.'),))
        return ProposalResult((CandidateBundle(request.plan.parent, request.baseline,
            HarnessSnapshot((component,)), self.generator_id,
            (EditReason(component.component_id, 'The reference omitted its final check.',
                        (request.records[0].run_id,)),)),))


class Executor:
    capabilities = frozenset()

    async def execute(self, plan, task, harness):
        return ExecutionRecord('run-' + uuid4().hex, task.task_id, task.material_id,
            harness.snapshot_id, plan.parent.state, plan.conditions_id, 'completed',
            harness.components[0].files[0].text, model_calls=0)


class Compose:
    async def compose(self, request, services):
        return request.candidates[0]


class Select:
    async def select(self, task, records):
        return SelectionDecision(records[0].run_id, 'Existing synthetic output')


async def main():
    document = ComponentDocument('prompt', 'system-prompt', 'H', 'text-v1',
        (ComponentFile('instructions.txt', 'Complete the task.'),))
    components = ComponentRegistry((FileComponentAdapter(document, lambda value: None, optimization=OptimizationSpec(document.role, 'documents')),))
    generators = GeneratorRegistry()
    generators.register('example-rule', Rule)
    plan = RunPlan('offline', SystemVersion(*(content_hash(v) for v in ('H', 'I', 'S'))),
                   ('prompt',), generator_id='example-rule')
    workflow = ComponentWorkflow(generators=generators, components=components,
        runner=Executor(), composer=Compose(), selector=Select())
    async with WorkflowServices(plan) as services:
        outcome = await workflow.run(plan, TaskMaterial('task', 'Create a deliverable.'),
                                     components.snapshot(), services)
    print(outcome.selected.output)
    print('Assurance: ' + outcome.decision.assurance)


if __name__ == '__main__':
    asyncio.run(main())
