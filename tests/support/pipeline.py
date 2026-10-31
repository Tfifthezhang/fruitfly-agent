"""Deterministic component-stage fixtures shared by pipeline behavior tests."""
from fruitfly_agent.improvement.contracts.optimization import OptimizationSpec
from dataclasses import replace
from fruitfly_agent.improvement.contracts.components import ComponentDocument, ComponentFile, HarnessSnapshot
from fruitfly_agent.lab.improvement.components import ComponentRegistry, FileComponentAdapter
from fruitfly_agent.improvement.contracts.candidates import CandidateBundle, EditReason
from fruitfly_agent.improvement.contracts.editing import ProposalResult
from fruitfly_agent.improvement.contracts.execution import ExecutionRecord
from fruitfly_agent.improvement.contracts.assessment import SelectionDecision
from fruitfly_agent.lab.improvement.editor.generators import GeneratorRegistry
from fruitfly_agent.lab.improvement.workflow import ImprovementWorkflow as ComponentWorkflow
from fruitfly_agent.improvement.contracts.plans import RunPlan
from fruitfly_agent.improvement.contracts.versions import SystemVersion, content_hash


def version():
    return SystemVersion(*(content_hash(v) for v in ('harness', 'improver', 'state')))


def fixture():
    docs = tuple(ComponentDocument(name, 'instructions', role, 'text-v1', (ComponentFile('instructions.txt', name),))
                 for name, role in (('prompt', 'H'), ('memory', 'S')))
    registry = ComponentRegistry(FileComponentAdapter(d, lambda doc: None, optimization=OptimizationSpec(d.role, 'documents', state='retained' if d.role == 'S' else 'frozen')) for d in docs)
    return registry, registry.snapshot()


class RuleGenerator:
    generator_id = 'rule-generator'
    required_capabilities = frozenset()

    def __init__(self):
        self.requests = []

    async def propose(self, request, services):
        services.check()
        self.requests.append(request)
        chosen = 'prompt' if request.scope == 'invariant' else 'memory'
        documents = tuple(replace(c, files=(ComponentFile('instructions.txt', c.files[0].text + ' improved'),))
                          if c.component_id == chosen else c for c in request.baseline.components)
        candidate = CandidateBundle(request.plan.parent, request.baseline, HarnessSnapshot(documents), self.generator_id,
            (EditReason(chosen, 'Observed missing behavior', (request.records[0].run_id,), expected_effect='The proposed behavior appears in the subsequent execution.'),))
        return ProposalResult((candidate,))


class RuleComposer:
    async def compose(self, request, services):
        documents = {c.component_id: c for c in request.baseline.components}
        for candidate in request.candidates:
            for name in candidate.changed_ids:
                documents[name] = candidate.harness.component(name)
        harness = HarnessSnapshot(tuple(documents.values()))
        names = [c.component_id for c in harness.components if c != request.baseline.component(c.component_id)]
        return CandidateBundle(request.plan.parent, request.baseline, harness, 'rule-composer',
            tuple(EditReason(name, 'Supported composition', (request.records[-1].run_id,), expected_effect='The proposed behavior appears in the subsequent execution.') for name in names))


class Runner:
    capabilities = frozenset()

    def __init__(self):
        self.calls = []

    async def execute(self, plan, task, harness):
        self.calls.append((plan, task, harness))
        return ExecutionRecord('run-' + str(len(self.calls)), task.task_id, task.material_id, harness.snapshot_id,
            plan.parent.state, plan.conditions_id, 'completed', '\n'.join(c.files[0].text for c in harness.components),
            model_calls=0)


class Selector:
    async def select(self, task, records):
        return SelectionDecision(records[-1].run_id, 'Existing last result')


def build_pipeline(**kwargs):
    components, baseline = fixture()
    generators = GeneratorRegistry()
    generators.register('rule-generator', RuleGenerator)
    runner = Runner()
    flow = ComponentWorkflow(generators=generators, components=components,
        runner=runner, composer=RuleComposer(), selector=Selector(), **kwargs)
    plan = RunPlan('job', version(), ('prompt', 'memory'), generator_id='rule-generator')
    return flow, plan, baseline, runner
