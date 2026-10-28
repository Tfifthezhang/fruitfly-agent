"""Prepared benchmark episodes for fixed-I comparisons through Lab's public ports."""
from copy import copy
from dataclasses import dataclass
import unicodedata

from fruitfly_agent.improvement.contracts.experiments import MaterialOption, PreparedExecution
from fruitfly_agent.improvement.contracts.versions import canonical_json, content_hash
from fruitfly_agent.improvement.contracts.failures import IntegrityError
from fruitfly_agent.lab.improvement.improver.episodes import NativeEpisodeExecutor
from fruitfly_agent.lab.improvement.improver.materials import FrozenMaterials
from fruitfly_agent.lab.improvement.improver.registration import comparison_definition
from fruitfly_agent.improvement.contracts.experiments import ExecutionRequest
from .assessment import OfficialMeasurements
from .runner import EvalTaskRunner


@dataclass(frozen=True)
class BenchmarkEpisode:
    prepared: PreparedExecution

    @property
    def adaptation(self):
        return self.prepared.task

    @property
    def evaluations(self):
        return (self.prepared.task,)


class BenchmarkEpisodeExecutor(NativeEpisodeExecutor):
    feedback = 'scored'

    def __init__(self, context, episode, parameters, *, executor=None):
        def runner_factory(config, registry, artifacts, services):
            host = copy(context)
            host.components, host.services = registry, services
            return EvalTaskRunner(host, episode.prepared.private, OfficialMeasurements(), executor=executor)
        super().__init__(context, episode, parameters, runner_factory=runner_factory)

    def evaluation_task(self, index, case):
        return case

    async def measure(self, runner, task, record, case, services):
        value = await runner.measurements.measure(task, record)
        if value is None:
            raise ValueError('benchmark episode has no official measurement')
        return value.score


def benchmark_improver(development, verification, *, material_id='benchmark-editor-study',
                       execution_id='benchmark-improver', max_verifications=1, executor=None):
    """Compose already registered one-task benchmark definitions into an I study.

    Both partitions must be nonempty and disjoint. Discovery and preparation are
    offline; running the returned definition launches the configured environments.
    """
    from fruitfly_agent.improvement.contracts.validation import identifier
    identifier(material_id)
    development, verification = tuple(development), tuple(verification)
    if (not development or not verification or len(development) > 8 or len(verification) > 8
            or type(max_verifications) is not int or not 1 <= max_verifications <= 10):
        raise ValueError('benchmark editor studies need 1–8 episodes per partition and 1–10 verification uses')
    def freeze(context, selected, target):
        if selected != material_id:
            raise ValueError('unknown benchmark editor material')
        partitions, seen = {}, set()
        for name, definitions in (('development', development), ('verification', verification)):
            episodes = []
            for definition in definitions:
                request = ExecutionRequest('', (), (target,), definition.execution_id, 'task', 'scored')
                prepared = definition.prepare(context, request)
                key = unicodedata.normalize('NFC', prepared.task.instruction).strip()
                if not key or key in seen:
                    raise ValueError('benchmark episode inputs overlap across tasks or partitions')
                seen.add(key)
                episodes.append(BenchmarkEpisode(prepared))
            partitions[name] = tuple(episodes)
        identity = content_hash(canonical_json({name: [e.prepared.source_id for e in episodes]
            for name, episodes in partitions.items()} | {'verification_uses': max_verifications}))
        verification_key = content_hash(canonical_json(sorted(
            unicodedata.normalize('NFC', e.adaptation.instruction).strip() for e in partitions['verification'])))
        return FrozenMaterials(material_id, 'Prepared benchmark editor comparison', partitions['development'],
            partitions['verification'], identity, verification_key, max_verifications)
    def listing(context):
        return (MaterialOption(material_id, 'Prepared benchmark editor comparison',
            'Nested prepared benchmarks; explicit runs use models and containers.'),)
    def validate(context, frozen, ids):
        for episode in (*frozen.development, *frozen.verification):
            if episode.prepared.current_source() != episode.prepared.source_id:
                raise IntegrityError('benchmark episode changed during preparation')
            for name in ids:
                if context.components.snapshot().component(name).role == 'I':
                    raise ValueError('benchmark inner search cannot edit I')
    def episode_factory(context, episode, params):
        if params['evaluation_model_calls'] < episode.prepared.private.model_calls:
            raise ValueError('evaluation allowance is smaller than the prepared benchmark model limit')
        return BenchmarkEpisodeExecutor(context, episode, params, executor=executor)
    definition = comparison_definition(execution_id=execution_id, freeze_materials=freeze, list_materials=listing,
        episode_factory=episode_factory, inner_capabilities=lambda context: EvalTaskRunner.capabilities |
        frozenset('tool:' + t.name for t in context.config.tools),
        validate_materials=validate)
    # Fail insufficient evaluation allowances during offline preparation.
    from dataclasses import replace
    prepare = definition.prepare
    def preparing(context, request):
        prepared = prepare(context, request)
        frozen, params, spec = prepared.private
        if any(params['evaluation_model_calls'] < e.prepared.private.model_calls
               for e in (*frozen.development, *frozen.verification)):
            raise ValueError('evaluation_model_calls must cover each benchmark model allowance')
        return prepared
    return replace(definition, prepare=preparing)
