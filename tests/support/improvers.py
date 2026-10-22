"""Explicit offline component ports; synthetic verification makes no quality claim."""
from dataclasses import replace
from queue import Queue
from uuid import uuid4
from unittest.mock import Mock

from fruitfly_agent.lab.improvement.api import (WorkflowBindings, GeneratorRegistry,
    CandidateBundle, ComponentFile, HarnessSnapshot, EditReason, ProposalResult,
    ExecutionRecord, SelectionDecision)
from fruitfly_agent.interactive.contracts.improvement import WorkflowRequest
from fruitfly_agent.run.application import RunApplicationFactory
from tests.support.materials import _write_models
from tests.support.faux_provider import FauxProvider
from tests.support.terminal import menu_choice


class QueueEditor:
    def __init__(self):
        self.lines = Queue()
        self.output = None
        self.offset = 0

    def read_line(self):
        line = self.lines.get(timeout=3)
        if self.output is not None:
            rendered = self.output.getvalue()[self.offset:]
            self.offset = len(self.output.getvalue())
            if line.startswith('@'):
                return menu_choice(line[1:], rendered)
        return line

    def send(self, *lines):
        for line in lines:
            self.lines.put(line)


class OfflineGenerator:
    generator_id = 'offline-rule'
    required_capabilities = frozenset()

    async def propose(self, request, services):
        documents = tuple(replace(c, files=(ComponentFile('instructions.txt',
            c.files[0].text + '\nUse exact answers.'),)) if c.component_id in request.plan.component_ids else c
            for c in request.baseline.components)
        return ProposalResult((CandidateBundle(request.plan.parent, request.baseline,
            HarnessSnapshot(documents), self.generator_id,
            tuple(EditReason(name, 'Synthetic offline contrast', (request.records[0].run_id,))
                  for name in request.plan.component_ids)),))


class FirstComposer:
    async def compose(self, request, services):
        return request.candidates[-1]


class FirstSelector:
    async def select(self, task, records):
        return SelectionDecision(records[-1].run_id, 'Synthetic offline choice of the executed revision')


class NoReflection:
    async def reflect(self, outcome):
        return ()


class SyntheticVerification:
    async def verify(self, outcome):
        return SelectionDecision(outcome.selected.run_id, 'Synthetic test verification only', 'verified')


class OfflineRunner:
    capabilities = frozenset({'file-workspace', 'tool:read', 'tool:write', 'tool:edit'})

    async def execute(self, plan, task, harness):
        return ExecutionRecord('run-' + uuid4().hex, task.task_id, task.material_id,
            harness.snapshot_id, plan.parent.state, plan.conditions_id, 'completed', 'offline result', model_calls=0)


def offline_factory(root, target='base_prompt'):
    _write_models(root)
    providers = Mock()
    providers.create.side_effect = lambda *_: FauxProvider()
    generators = GeneratorRegistry()
    generators.register('offline-rule', OfflineGenerator)
    factory = RunApplicationFactory(cwd=root, environment={}, provider_registry=providers,
        improvement_bindings=WorkflowBindings(generators=generators,
            runner=lambda *args: OfflineRunner(), composer=lambda *args: FirstComposer(),
            selector=lambda *args: FirstSelector(), reflector=lambda *args: NoReflection(),
            verifier=SyntheticVerification()))
    factory.test_request = WorkflowRequest('Complete the synthetic task.', component_ids=(target,),
        generator_id='offline-rule', scope='persistent')
    factory.configuration.save()
    factory.reload_configuration()
    return factory


async def improve(app, factory, direction='improve'):
    preview = app.workflow_preview(replace(factory.test_request, direction=direction))
    return await app.improve(direction, preview_token=preview.preview_token)
