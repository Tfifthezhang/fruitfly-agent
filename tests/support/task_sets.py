"""Deterministic collection execution with observable parallelism and no models."""
import asyncio
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

from fruitfly_agent.lab.improvement.api import (TaskEntry, ScoreSpec, TaskSetSnapshot, CollectionBinding,
    TaskMaterial, ExecutionRecord, Measurement, CandidateBundle, ComponentFile, HarnessSnapshot,
    EditReason, ProposalResult, ExecutionContext, ExecutionPorts, content_hash)


class IncrementGenerator:
    generator_id = 'increment'
    required_capabilities = frozenset()
    supports_task_sets = True

    def __init__(self): self.requests = []

    async def propose(self, request, services):
        self.requests.append(request)
        name = request.plan.component_ids[0]
        document = request.baseline.component(name)
        document = replace(document, files=(ComponentFile('instructions.txt', document.files[0].text + '+'),))
        harness = HarnessSnapshot(tuple(document if c.component_id == name else c for c in request.baseline.components))
        return ProposalResult((CandidateBundle(request.plan.parent, request.baseline, harness, self.generator_id,
            (EditReason(name, 'Synthetic observed hypothesis', (request.records[0].run_id,)),)),))


def collection(name, count=2, *, limit=2, score=None, partition='development', source=None):
    state = SimpleNamespace(active=0, peak=0, calls=[], cleaned=0)
    entries = tuple(TaskEntry(name + '-' + str(i), name, content_hash(source or name), name,
        TaskMaterial(name + '-' + str(i), 'Complete fixture ' + name + ' ' + str(i)),
        ScoreSpec('fixture-score'), name + '/' + str(i), partition=partition, model_limit=limit) for i in range(count))
    class Measurements:
        async def measure(self, task, record):
            return Measurement(record.run_id, 'fixture-score', float(record.output))
    class Runner:
        capabilities = frozenset({'file-workspace'})
        def __init__(self, context): self.context = context
        async def execute(self, plan, task, harness):
            state.active += 1
            state.peak = max(state.peak, state.active)
            state.calls.append((task.task_id, harness.snapshot_id))
            try:
                self.context.services.reserve('model')
                await asyncio.sleep(0)
                value = score(task, harness) if score else float(any('+' in c.files[0].text for c in harness.components))
                return ExecutionRecord('leaf-' + uuid4().hex, task.task_id, task.material_id, harness.snapshot_id,
                    plan.parent.state, plan.conditions_id, 'completed', str(value), model_calls=1)
            finally:
                state.active -= 1
        async def aclose(self): state.cleaned += 1
    binding = CollectionBinding(entries, lambda context: ExecutionPorts(Runner(context), Measurements()),
        lambda: content_hash(source or name), content_hash(source or name), Runner.capabilities)
    return binding, state
