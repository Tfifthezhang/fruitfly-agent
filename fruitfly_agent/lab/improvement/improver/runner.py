"""Specialize common paired execution for fixed-I self-improvement."""
from fruitfly_agent.lab.improvement.execution.episodes import EpisodeTaskRunner, EpisodeMeasurements
from .episodes import ComparisonEpisodeExecutor


class ImproverTaskRunner(EpisodeTaskRunner):
    capabilities = frozenset({'improver-comparison'})

    def __init__(self, context, frozen, parameters, spec, *, episode_factory=None):
        if episode_factory is None:
            if context.runner_factory is None:
                raise ValueError('I comparison requires an explicitly registered episode executor or TaskRunner')
            episode_factory = lambda context, episode, parameters: ComparisonEpisodeExecutor(
                context, episode, parameters, runner_factory=context.runner_factory)
        super().__init__(context, frozen, parameters, spec, roles={'I'}, episode_factory=episode_factory,
            instruction_source=lambda context, harness: context.components.adapters['improvement-editor'].to_text(
                harness.component('improvement-editor')))


class TrialMeasurements(EpisodeMeasurements):
    pass
