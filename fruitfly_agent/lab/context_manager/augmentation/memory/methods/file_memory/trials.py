"""Measure memory H through isolated learning and downstream task execution."""
from copy import deepcopy
import asyncio
from dataclasses import asdict, dataclass, replace
from inspect import isawaitable
import json
from typing import Any

from fruitfly_agent.improvement.contracts.experiments import (
    EpisodeResult, ExecutionDefinition, ExecutionParameter, ExecutionPorts, PreparedExecution)
from fruitfly_agent.improvement.contracts.pipeline import ImprovementOutcome
from fruitfly_agent.improvement.contracts.plans import RunPlan
from fruitfly_agent.improvement.contracts.components import HarnessSnapshot, ComponentFile
from fruitfly_agent.improvement.contracts.tasks import TaskMaterial
from fruitfly_agent.improvement.contracts.versions import canonical_json, content_hash
from fruitfly_agent.improvement.stages.services import StageServices
from fruitfly_agent.lab.improvement.components import TextComponentAdapter
from fruitfly_agent.lab.improvement.execution.episodes import EpisodeTaskRunner, EpisodeMeasurements
from fruitfly_agent.lab.improvement.verification.episodes import PairedEpisodeVerification
from fruitfly_agent.lab.improvement.materials.episodes import FrozenEpisode, freeze, materials


@dataclass(frozen=True)
class MemoryEpisode:
    source: FrozenEpisode

    @property
    def learning_inputs(self):
        return tuple(case.input for case in self.source.suite.train)

    @property
    def adaptation(self):
        return TaskMaterial('memory-learning', canonical_json(self.learning_inputs))

    @property
    def evaluations(self):
        return (*self.source.suite.validation, *self.source.holdout)

    @property
    def suite(self):
        return self.source.suite


@dataclass(frozen=True)
class MemoryStudy:
    source_id: str
    initial_harness_id: str
    conditions_id: str
    inner_components: tuple[str, ...] = ('memory-library',)


def freeze_materials(context, identity):
    captured = freeze(context, identity, 'file-memory')
    if any(not isinstance(episode, FrozenEpisode)
           for episode in (*captured.development, *captured.verification)):
        raise ValueError('memory learning requires frozen task-package episodes')
    return replace(captured,
        development=tuple(MemoryEpisode(episode) for episode in captured.development),
        verification=tuple(MemoryEpisode(episode) for episode in captured.verification))


class MemoryEpisodeExecutor:
    """Receive learning inputs without their expected outputs; retain no production writer."""
    def __init__(self, context, episode, parameters):
        self.context, self.episode, self.parameters = context, episode, parameters

    async def run(self, request, *, signal):
        context = self.context
        if context.component_ids != ('file-memory',):
            raise ValueError('memory learning changes exactly the File memory H component')
        factory = (context.resource_factories or {}).get('memory-learning')
        if factory is None:
            raise ValueError('memory learning requires an owner-provided worker factory')
        registry = deepcopy(context.components)
        baseline = request.baseline
        candidate = request.candidate or baseline
        adapter = registry.adapters['file-memory']
        values = adapter.target.parse(adapter.to_text(candidate.component('file-memory')))
        state = registry.adapters['memory-library'].target
        documents = state.retained_documents
        plan = RunPlan(request.episode_id, context.plan.parent, ('file-memory', 'memory-library'),
            timeouts=context.plan.timeouts, retain_experience=False)
        services = StageServices(plan, signal=signal,
            record=lambda event, **fields: context.services.record(event, episode_id=request.episode_id, **fields))
        source = 'study-' + content_hash(request.task.instruction)[7:31]
        checkpoint: dict[str, Any] = {'pending': {}, 'processed': 0, 'consolidated_turns': 0,
                                   'evidence': [], 'operations': {}}
        inputs = tuple(self.episode.learning_inputs)
        originals = {}
        try:
            if values['maintenance_enabled']:
                worker = factory(values)
                for index, text in enumerate(inputs):
                    identity = source + ':user-' + str(index + 1)
                    row = {'identity': identity, 'session_id': source, 'message_id': 'user-' + str(index + 1),
                        'chars': len(text), 'completed': True}
                    originals[identity] = text
                    checkpoint['evidence'].append(row)
                    work = worker.request(checkpoint, documents)
                    if work is None:
                        continue
                    async with asyncio.timeout(worker.config.timeout_seconds):
                        changed, processed, turns = await services.operation(worker.generate(work, checkpoint,
                            lambda row: originals[row['identity']], on_call=lambda: services.observe('model')), stage='execute')
                    checkpoint['operations'][str(index)] = {'status': 'completed',
                        'operation': work['operation'], 'request_id': work['request_id']}
                    if changed is not None:
                        documents = canonical_json(state.validate_documents(json.loads(changed)))
                    if processed is not None:
                        checkpoint['processed'] = processed
                    if turns is not None:
                        checkpoint['consolidated_turns'] = turns
            entries = state.validate_documents(json.loads(documents))
            local = state.with_state_change(entries)
            state_adapter = TextComponentAdapter(local, state.component_kind)
            registry.adapters['memory-library'] = state_adapter
            import yaml
            document = candidate.component('memory-library')
            changed = document
            if documents != state.retained_documents:
                payload = yaml.safe_load(document.files[0].text)
                payload['parameters']['content']['documents'] = documents
                changed = replace(document, files=(ComponentFile('parameters.yaml', yaml.safe_dump(payload)),))
            state_adapter.validate(changed)
            after = HarnessSnapshot(tuple(changed if c.component_id == 'memory-library' else c for c in candidate.components))
            runner = services.own(context.runner_factory(plan, registry, context.artifacts, services))
            before_scores, after_scores, records = [], [], []
            for index, case in enumerate(self.episode.evaluations):
                task = TaskMaterial('memory-check-' + str(index), case.input)
                scores = []
                for harness in (baseline, after):
                    services.observe('execution')
                    record = await services.operation(runner.execute(plan, task, harness), stage='execute')
                    if (record.status != 'completed' or record.harness_id != harness.snapshot_id
                            or record.task_id != task.task_id or record.material_id != task.material_id
                            or record.initial_state_id != plan.parent.state or record.conditions_id != plan.conditions_id):
                        raise ValueError('memory learning execution receipt mismatch')
                    measured = self.episode.suite.evaluation_policy.score(record.output, case)
                    if isawaitable(measured):
                        measured = await services.operation(measured, stage='evaluator')
                    if not 0 <= measured.score <= 1:
                        raise ValueError('memory learning requires normalized scores')
                    scores.append(measured.score)
                    records.append(record)
                before_scores.append(scores[0]); after_scores.append(scores[1])
            if not records:
                raise ValueError('memory learning requires downstream validation cases')
            outcome = ImprovementOutcome(plan, request.task, records[-1], after, (), tuple(records), None)
            return EpisodeResult(request.episode_id, outcome, services.used['model'], services.used['execution'],
                tuple(before_scores), tuple(after_scores))
        finally:
            await services.close()
            for kind, amount in services.used.items():
                context.services.observe(kind, amount)


def definition():
    def prepare(context, request):
        if request.component_ids != ('file-memory',) or request.input_paths:
            raise ValueError('memory learning selects File memory H; episode packages own learning inputs')
        if context.runner_factory is None or 'memory-learning' not in (context.resource_factories or {}):
            raise ValueError('memory learning needs an isolated downstream runner and owner worker factory')
        baseline = context.components.snapshot()
        baseline.component('memory-library')
        parameters = definition().normalize(request.parameters)
        captured = freeze_materials(context, request.material_id)
        if (request.scope == 'persistent' and context.remaining_verification is not None
                and context.remaining_verification(captured.verification_key, captured.max_verifications) == 0):
            raise ValueError('independent verification use limit exhausted; provide new material')
        spec = MemoryStudy(captured.source_id, baseline.snapshot_id,
            content_hash(canonical_json({'plan': asdict(context.plan), 'source': captured.source_id, 'parameters': parameters})))
        return PreparedExecution(TaskMaterial('memory-study',
            'Improve the granted File memory execution instructions and settings. Compare isolated learning '
            'from identical initial memory and downstream recall. Preserve sources, model bindings and evaluation.',
            environment_id='memory-learning-v1', origin='experiment:' + request.material_id), captured.source_id,
            (('Experiment', captured.name), ('Learning', 'Training inputs only; trial-local validated adoption'),
             ('Evaluation', 'Validation and holdout answers stay private'), ('Initial state', context.plan.parent.state)),
            lambda: freeze_materials(context, request.material_id).source_id, (captured, parameters, spec))
    def build(context, prepared):
        captured, parameters, spec = prepared.private
        runner = context.services.own(EpisodeTaskRunner(context, captured, parameters, spec,
            roles={'H'}, episode_factory=MemoryEpisodeExecutor, instruction_source=lambda *_: ''))
        verifier = PairedEpisodeVerification(runner, context.claim_verification)
        return ExecutionPorts(runner, EpisodeMeasurements(runner), verifier, retain_experience=False)
    return ExecutionDefinition('memory-learning', 'File memory learning comparison', 'memory-learning-v1',
        frozenset({'H'}), frozenset({'configuration-materialization', 'memory-learning'}), materials, prepare, build,
        (ExecutionParameter('repetitions', 'Paired repetitions', 'integer', 2, 2, 10),
         ExecutionParameter('min_gain', 'Minimum paired gain', 'number', 0.0, 0, 1),
         ExecutionParameter('max_regression', 'Maximum case regression', 'number', 0.0, 0, 1)),
        defaults=(('scope', 'persistent'),), component_scope=lambda context, material, ids: ('file-memory',),
        material_snapshot=lambda context, material, parameters: freeze_materials(context, material),
        persistent_policy=PairedEpisodeVerification.policy_id, required_components=('file-memory',),
        requires_runner_factory=True)
