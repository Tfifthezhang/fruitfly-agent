"""Fixed-depth I trials. Each invocation evaluates one editor, never adopts it."""
from dataclasses import asdict
from uuid import uuid4

from fruitfly_agent.improvement.contracts.experiments import EpisodeRequest, TrialReport
from fruitfly_agent.improvement.contracts.pipeline import ExecutionRecord, Measurement, Resource, TaskMaterial, canonical_json
from fruitfly_agent.improvement.contracts.versions import content_hash
from fruitfly_agent.improvement.workflow.budget import AllocationExhausted
from .episodes import NativeEpisodeExecutor
from fruitfly_agent.improvement.contracts.failures import IntegrityError
from fruitfly_agent.improvement.execution.facts import attach_facts, receipt_facts
from fruitfly_agent.improvement.contracts.facts import BudgetFact


class ImproverTaskRunner:
    capabilities = frozenset({'improver-comparison'})
    execution_charge = 0

    def __init__(self, context, frozen, parameters, spec, *, episode_factory=NativeEpisodeExecutor):
        self.context, self.materials, self.parameters, self.spec = context, frozen, parameters, spec
        self.episode_factory = episode_factory
        self.reports = {}
        self.trials = 0

    def allocation(self, partition):
        episodes = getattr(self.materials, partition)
        evaluations = sum(2 * len(e.evaluations) for e in episodes)
        repeats = self.parameters['repetitions']
        return {'model': repeats * (len(episodes) * self.parameters['inner_model_calls'] +
                    evaluations * self.parameters['evaluation_model_calls']),
                'execution': repeats * (len(episodes) * self.parameters['inner_executions'] + evaluations)}

    async def trial(self, harness, partition, *, repeats=None):
        context, params = self.context, self.parameters
        context.components.validate(harness)
        baseline = context.components.snapshot()
        if any(c != baseline.component(c.component_id) for c in harness.components if c.role != 'I'):
            raise ValueError('I trials must preserve all H/S components')
        instructions = harness.component('improvement-editor').files[0].text
        i_documents = tuple(c for c in harness.components if c.role == 'I')
        instructions_id = (content_hash(instructions) if len(i_documents) == 1
                           else content_hash(canonical_json([asdict(c) for c in i_documents])))
        gains, regressions, evidence, identities, case_gains = [], [], [], [], []
        start = dict(context.services.used)
        failures = 0
        for repeat in range(params['repetitions']) if repeats is None else repeats:
            for episode in getattr(self.materials, partition):
                identity = 'episode-' + uuid4().hex
                evaluations = 2 * len(episode.evaluations)
                budget = context.services.budget.child({
                    'model': params['inner_model_calls'] + evaluations * params['evaluation_model_calls'],
                    'execution': params['inner_executions'] + evaluations})
                request = EpisodeRequest(identity, instructions, baseline, self.spec.inner_components,
                    episode.adaptation, repeat,
                    improver=harness)
                context.services.record('episode-start', episode_id=identity, partition=partition,
                    instructions_id=instructions_id, experiment_id=self.spec.conditions_id, repeat=repeat)
                try:
                    executor = self.episode_factory(context, episode, params)
                    result = await context.services.operation(executor.run(request, budget=budget, signal=context.services.signal))
                    if (result.episode_id != identity or not result.scores_before or
                            len(result.scores_before) != len(episode.evaluations) or
                            len(result.scores_after) != len(result.scores_before) or
                            result.outcome.stop_reason in {'budget_exhausted', 'reference_unavailable'}):
                        raise ValueError('episode evidence is incomplete')
                    values = tuple(b - a for a, b in zip(result.scores_before, result.scores_after))
                    gains.append(sum(values) / len(values))
                    case_gains.append(values)
                    regressions.append(min(values))
                    identities.append(identity)
                    ref = context.artifacts.put(canonical_json(asdict(result)).encode())
                    evidence.append(ref)
                    context.services.record('episode-finished', episode_id=identity, evidence=ref,
                        model_calls=budget.used['model'], executions=budget.used['execution'])
                except (AllocationExhausted, IntegrityError):
                    raise
                except (ValueError, RuntimeError, TimeoutError) as exc:
                    failures += 1
                    context.services.record('episode-failed', episode_id=identity, error=type(exc).__name__)
                finally:
                    budget.close()
        report = TrialReport(self.spec.conditions_id, instructions_id, self.spec.initial_harness_id, partition,
            tuple(gains), tuple(regressions), failures,
            context.services.used['model'] - start['model'], context.services.used['execution'] - start['execution'],
            tuple(identities), tuple(evidence), case_gains=tuple(case_gains))
        return report

    async def execute(self, plan, task, harness):
        if plan != self.context.plan:
            raise ValueError('I runner belongs to another frozen plan')
        if self.trials >= self.parameters['max_trials']:
            raise AllocationExhausted('development trial limit exhausted')
        self.trials += 1
        report = await self.trial(harness, 'development')
        reference = self.context.artifacts.put(canonical_json(asdict(report)).encode())
        run_id = 'trial-' + uuid4().hex
        self.reports[run_id] = report
        record = ExecutionRecord(run_id, task.task_id, task.material_id, harness.snapshot_id,
            plan.parent.state, plan.conditions_id, 'error' if report.failures else 'completed',
            f'Development improvement gain: {report.mean_gain:.6f}; failures: {report.failures}; '
            f'model calls: {report.model_calls}. This is not independent verification.',
            (Resource('trial-report.json', reference, 'application/json', 'diagnostic'),), report.model_calls)
        facts = receipt_facts(record, self.context.artifacts,
            termination_reason='episode_failed' if report.failures else 'composite_completed',
            budgets=(BudgetFact('model_calls', 'composite', report.model_calls, source='paired development trial'),
                     BudgetFact('executions', 'composite', report.executions, source='paired development trial')),
            counters=(('episode_failures', report.failures),), children=report.evidence)
        return attach_facts(record, facts, self.context.artifacts)


class TrialMeasurements:
    direction = 'max'

    def __init__(self, runner):
        self.runner = runner

    async def measure(self, task, record):
        report = self.runner.reports.get(record.run_id)
        if report is None or report.failures or record.status != 'completed':
            return None
        if (report.experiment_id != self.runner.spec.conditions_id or
                report.initial_harness_id != self.runner.spec.initial_harness_id):
            raise ValueError('trial measurement identity mismatch')
        return Measurement(record.run_id, 'improver-development-v1', report.mean_gain,
            'Measured downstream gain on development episodes; not independent assurance.')
