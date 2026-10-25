"""Task-set search operations for the shared engine, with separate formal selection."""
from dataclasses import asdict
import time
from uuid import uuid4

from ..contracts.editing import TaskSetProposalRequest, ProposalResult
from ..contracts.candidates import CandidateBundle
from ..contracts.evaluation import CandidateEvaluation
from ..contracts.evaluation import EvaluationBatch, JointSelection, TaskSetOutcome
from ..contracts.assessment import AssessmentUnavailable
from ..contracts.assessment import Measurement
from ..contracts.stopping import SearchState, StopDecision, stop_reason
from ..contracts.versions import content_hash, canonical_json
from ..execution.batches import BatchEvaluator
from ..assessment.promotion import compare_candidates
from ..assessment.joint import assess_batch
from ..assessment.joint_process import choose_seed
from ..task_sets.sampling import sample_batch
from .budget import AllocationExhausted
from .engine import SearchEngine
from .problems import SearchProblem
from .services import GeneratorServices


class TaskSetProblem:
    def __init__(self, context, snapshot, bindings, settings, *, evaluator_factory=BatchEvaluator,
                 sample=sample_batch, aggregate=assess_batch, compare=compare_candidates):
        self.context, self.snapshot, self.bindings, self.settings = context, snapshot, bindings, settings
        self.evaluator_factory, self.sample, self.aggregate, self.compare = evaluator_factory, sample, aggregate, compare

    async def run(self, workflow, plan, material, baseline, services, *, experience=()):
        if material != self.snapshot or services.plan != plan:
            raise ValueError('task-set search differs from prepared material')
        if plan.purpose != 'task' or plan.retain_experience:
            raise ValueError('task-set development search neither adopts nor commits experience')
        schedule = workflow.strategies.get(plan.strategy_id).schedule(plan)
        if len(schedule.missions) != 1 or schedule.compositions or schedule.references != 1:
            raise ValueError('task-set search currently needs one sequential candidate per round')
        workflow.components.validate(baseline)
        for component in plan.component_ids:
            document = baseline.component(component)
            required: frozenset[str] = getattr(workflow.components.adapters[component], 'required_capabilities', frozenset())
            if any(document.role not in b.roles or required - b.capabilities for b in self.bindings):
                raise ValueError('an editable component is unsupported by a task collection')
        generator = services.own(workflow.generators.create(plan.generator_id))
        if not getattr(generator, 'supports_task_sets', False):
            raise ValueError('candidate generator does not declare task-set evidence support')
        available = {'editor', 'model', 'measurements'}
        if services.editor is None:
            available.discard('editor')
        if services.completer is None:
            available.discard('model')
        if generator.required_capabilities - available:
            raise ValueError('candidate generator lacks required capabilities')
        evaluator = self.evaluator_factory(self.context, self.snapshot, self.bindings, self.settings,
            aggregate=self.aggregate, assessment=workflow.completed_assessment)
        evaluator.persist('materials', 'task-set', asdict(self.snapshot))
        entries = self.snapshot.selection_entries()
        selection_batch = EvaluationBatch(self.snapshot.snapshot_id, tuple(e.key for e in entries),
            'selection', self.settings.execution.attempts)
        limits = {'model': 2 * sum(e.model_limit for e in entries) * selection_batch.attempts,
                  'execution': 2 * sum(e.execution_limit for e in entries) * selection_batch.attempts}
        final_budget = services.budget.child(limits)
        candidates: list[CandidateBundle] = []
        exploration: list[dict[str, str]] = []
        harnesses = {baseline.snapshot_id: baseline}
        official, provisional, decision = None, None, None
        official_harness = baseline
        batch = self.sample(self.snapshot, self.settings.sampling, 0, attempts=self.settings.execution.attempts)
        round_evaluations = []
        reference: tuple[CandidateEvaluation, ...] = ()
        prior: tuple[CandidateBundle, ...] = ()
        no_gain, failures = 0, 0
        started = time.monotonic()
        round_number = 0
        final_compared = False

        async def evaluate(harness, target=None):
            harnesses[harness.snapshot_id] = harness
            return await services.operation(evaluator.evaluate(plan, harness, target or batch))

        async def begin(index, current):
            nonlocal batch, round_evaluations, reference, prior, provisional, round_number
            round_number = index + 1
            batch = self.sample(self.snapshot, self.settings.sampling, index, attempts=self.settings.execution.attempts)
            incumbent = await evaluate(current)
            round_evaluations = [incumbent]
            reference = tuple(e for e in evaluator.evaluations if e.batch.phase == 'search')
            prior = tuple(candidates)
            provisional = incumbent

        async def propose(current, scope, index):
            keys = {key for e in reference for key in e.batch.task_keys}
            request = TaskSetProposalRequest(plan, self.snapshot.snapshot_id,
                tuple(e for e in self.snapshot.partition('development') if e.key in keys), current,
                reference, scope, index, prior)
            proposal = await services.operation(generator.propose(request, GeneratorServices(services)))
            if not isinstance(proposal, ProposalResult) or len(proposal.candidates) > 1:
                raise ValueError('task-set search needs at most one candidate per round')
            for candidate in proposal.candidates:
                workflow.validate(candidate, plan=plan, baseline=current, records=request.records)
                candidates.append(candidate)
            return proposal

        async def probe(harness):
            nonlocal failures
            result = await evaluate(harness)
            round_evaluations.append(result)
            failures = 0 if result.complete else failures + 1

        async def compose(*args):
            raise ValueError('task-set composition is not enabled')

        async def promote(*, final):
            nonlocal official, official_harness, decision, no_gain, final_compared
            if provisional is None or not provisional.complete:
                return
            challenger = harnesses[provisional.harness_id]
            if not final:
                # Keep final comparison protected if exploratory promotion cannot fit.
                if any(services.budget.available(k) < v for k, v in limits.items()):
                    services.record('promotion-deferred', reason='final comparison quota remains protected')
                    return
            async def compare():
                nonlocal official, official_harness, decision, no_gain
                before = await evaluate(official_harness, selection_batch)
                after = await evaluate(challenger, selection_batch)
                comparison = self.compare(before, after, self.settings.promotion)
                evaluator.persist('comparisons', 'comparison-' + uuid4().hex, asdict(comparison))
                if before.complete:
                    official = before
                    decision = JointSelection(before.evaluation_id, 'Incumbent on the complete shared selection set')
                if comparison.result == 'better':
                    official, official_harness = after, challenger
                    decision = JointSelection(after.evaluation_id, 'Improved on the complete shared selection set')
                    no_gain = 0
                elif comparison.result != 'insufficient':
                    no_gain += 1
            if final:
                with services.phase(final_budget):
                    await compare()
                final_compared = True
            else:
                await compare()

        async def select(index, last):
            nonlocal provisional
            complete = [e for e in round_evaluations if e.complete]
            if complete:
                provisional = max(complete, key=lambda e: e.assessment.score)
            if last or (index + 1) % self.settings.promotion.every_rounds == 0:
                await promote(final=last)

        def stop(index, count, repeated, requested):
            state = SearchState(index, schedule.rounds, count, False, requested,
                measurements=(Measurement(official.evaluation_id, 'joint-development-v1', official.assessment.score),)
                    if official is not None and official.assessment.score is not None else (),
                incumbent_run_id=official.evaluation_id if official else None,
                model_calls=services.used['model'], executions=services.used['execution'],
                consecutive_no_gain=no_gain, consecutive_failures=failures, elapsed_seconds=time.monotonic() - started)
            value = workflow.stop_policy.decide(state)
            if value:
                services.record('stop-decision', reason=stop_reason(value), phase='round',
                    evidence_ids=list(value.evidence_ids) if isinstance(value, StopDecision) else [])
            return stop_reason(value)

        async def advance(current):
            chosen = provisional or round_evaluations[0]
            reason = 'Best complete result on this shared development batch; ties retain its incumbent.'
            if workflow.exploration is not None and getattr(workflow.exploration, 'process_guided', False):
                chosen, reason = await choose_seed(workflow.completed_assessment, self.snapshot, tuple(round_evaluations), chosen)
            row = {'evaluation_id': chosen.evaluation_id, 'harness_id': chosen.harness_id, 'reason': reason}
            exploration.append(row)
            services.record('exploration-selected', **row)
            return harnesses[chosen.harness_id]

        reason = 'completed'
        try:
            result = await evaluate(baseline)
            if not result.complete:
                reason = 'reference_unavailable'
            else:
                provisional = result
                reason = await SearchEngine().run(schedule, baseline, SearchProblem(
                    begin, propose, probe, compose, select, stop, advance, services.record))
                if not final_compared:
                    await promote(final=True)
        except AllocationExhausted:
            reason = 'budget_exhausted'
            try:
                await promote(final=True)
            except AllocationExhausted:
                pass
        except AssessmentUnavailable:
            reason = 'assessment_unavailable'
        finally:
            final_budget.close()
        return TaskSetOutcome(plan, self.snapshot, official, official_harness, tuple(candidates),
            tuple(evaluator.evaluations), decision, reason, tuple(exploration))
