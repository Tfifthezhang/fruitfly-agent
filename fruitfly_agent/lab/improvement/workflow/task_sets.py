"""Task-set search operations for the shared engine, with separate formal selection."""
from dataclasses import asdict, replace
import inspect
from fruitfly_agent.improvement.workflow.state import WorkflowState
import time
from uuid import uuid4
from fruitfly_agent.improvement.contracts.editing import TaskSetProposalRequest, ProposalResult
from fruitfly_agent.improvement.contracts.candidates import CandidateBundle
from fruitfly_agent.improvement.contracts.evaluation import CandidateEvaluation
from fruitfly_agent.improvement.contracts.evaluation import EvaluationBatch, JointSelection, TaskSetOutcome
from fruitfly_agent.improvement.contracts.assessment import AssessmentUnavailable
from fruitfly_agent.improvement.contracts.assessment import Measurement
from fruitfly_agent.improvement.contracts.stopping import SearchState, StopDecision, stop_reason
from fruitfly_agent.improvement.contracts.versions import content_hash, canonical_json
from fruitfly_agent.improvement.execution.batches import BatchEvaluator
from ..assessment.promotion import compare_candidates
from ..assessment.joint import assess_batch
from ..assessment.joint_process import choose_seed
from ..task_sets.sampling import sample_batch
from fruitfly_agent.improvement.workflow.budget import AllocationExhausted
from fruitfly_agent.improvement.workflow.engine import SearchEngine, validate_schedule
from fruitfly_agent.improvement.workflow.problems import SearchProblem
from fruitfly_agent.improvement.workflow.services import GeneratorServices
from fruitfly_agent.improvement.workflow.operations import run_stage, diagnostic_reference, require_type
from fruitfly_agent.improvement.contracts.failures import StageFailure, Failure

class TaskSetProblem:

    def __init__(self, context, snapshot, bindings, settings, *, evaluator_factory=BatchEvaluator, sample=sample_batch, aggregate=assess_batch, compare=compare_candidates):
        self.context, self.snapshot, self.bindings, self.settings = (context, snapshot, bindings, settings)
        self.evaluator_factory, self.sample, self.aggregate, self.compare = (evaluator_factory, sample, aggregate, compare)

    async def run(self, workflow, plan, material, baseline, services, *, experience=()):
        if material != self.snapshot or services.plan != plan:
            raise ValueError('task-set search differs from prepared material')
        if plan.purpose != 'task' or plan.retain_experience:
            raise ValueError('task-set development search neither adopts nor commits experience')
        schedule = workflow.strategies.get(plan.strategy_id).schedule(plan)
        validate_schedule(schedule, plan)
        if len(schedule.missions) != 1 or schedule.compositions or schedule.references != 1:
            raise ValueError('task-set search currently needs one sequential candidate per round')
        for binding in self.bindings:
            workflow.components.admit(plan.component_ids, binding.capabilities)
        workflow.components.validate(baseline)
        for component in plan.component_ids:
            document = baseline.component(component)
            required: frozenset[str] = getattr(workflow.components.adapters[component], 'required_capabilities', frozenset())
            if any((document.role not in b.roles or required - b.capabilities for b in self.bindings)):
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
        evaluator = self.evaluator_factory(self.context, self.snapshot, self.bindings, self.settings, aggregate=self.aggregate, assessment=workflow.completed_assessment)
        evaluator.persist('materials', 'task-set', asdict(self.snapshot))
        entries = self.snapshot.selection_entries()
        selection_batch = EvaluationBatch(self.snapshot.snapshot_id, tuple((e.key for e in entries)), 'selection', self.settings.execution.attempts)
        limits = {'model': 2 * sum((e.model_limit for e in entries)) * selection_batch.attempts, 'execution': 2 * sum((e.execution_limit for e in entries)) * selection_batch.attempts}
        final_budget = services.budget.child(limits)
        state = services.state = WorkflowState(baseline)
        candidates: list[CandidateBundle] = []
        exploration: list[dict[str, str]] = []
        harnesses = {baseline.snapshot_id: baseline}
        official, provisional, decision = (None, None, None)
        official_harness = baseline
        batch = self.sample(self.snapshot, self.settings.sampling, 0, attempts=self.settings.execution.attempts)
        round_evaluations = []
        reference: tuple[CandidateEvaluation, ...] = ()
        prior: tuple[CandidateBundle, ...] = ()
        no_gain, failures = (0, 0)
        started = time.monotonic()
        round_number = 0
        final_compared = False

        async def evaluate(harness, target=None):
            harnesses[harness.snapshot_id] = harness
            services.check()
            await services.emit('before_trial', {'harness_id': harness.snapshot_id})
            result = await run_stage(services, 'execute', lambda: evaluator.evaluate(plan, harness, target or batch),
                validator=lambda value: require_type(value, CandidateEvaluation))
            # Private selection receipts never enter research/editor hooks.
            if (target or batch).phase == 'search':
                for trial in result.trials:
                    if trial.record is not None:
                        await services.emit('after_trial', {'receipt': asdict(trial.record)})
            return result

        async def begin(index, current):
            nonlocal batch, round_evaluations, reference, prior, provisional, round_number
            round_number = index + 1
            batch = self.sample(self.snapshot, self.settings.sampling, index, attempts=self.settings.execution.attempts)
            incumbent = await evaluate(current)
            round_evaluations = [incumbent]
            reference = tuple((e for e in evaluator.evaluations if e.batch.phase == 'search'))
            prior = tuple(candidates)
            provisional = incumbent

        async def propose(current, scope, index):
            keys = {key for e in reference for key in e.batch.task_keys}
            request = TaskSetProposalRequest(plan, self.snapshot.snapshot_id, tuple((e for e in self.snapshot.partition('development') if e.key in keys)), current, reference, scope, index, prior)
            contribution = await services.emit('before_proposal', {'harness_id': current.snapshot_id})
            request = replace(request, context=contribution.resources)
            proposal = await run_stage(services, 'propose', lambda: generator.propose(request, GeneratorServices(services)))
            if not isinstance(proposal, ProposalResult) or len(proposal.candidates) > 1:
                raise StageFailure(Failure('propose', 'invalid_result', 'ValueError'))
            for candidate in proposal.candidates:
                await run_stage(services, 'propose', lambda: workflow.validate(candidate, plan=plan, baseline=current, records=request.records))
                candidates.append(candidate)
                services.record('candidate-validated', candidate=asdict(candidate))
                await services.emit('after_candidate_validated', {'candidate_id': candidate.candidate_id, 'harness_id': candidate.harness.snapshot_id, 'reasons': [asdict(r) for r in candidate.reasons]})
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
                if any((services.budget.available(k) < v for k, v in limits.items())):
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
                    official, official_harness = (after, challenger)
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

        async def stop(index, count, repeated, requested):
            state = SearchState(index, schedule.rounds, count, False, requested, measurements=(Measurement(official.evaluation_id, 'joint-development-v1', official.assessment.score),) if official is not None and official.assessment.score is not None else (), incumbent_run_id=official.evaluation_id if official else None, model_calls=services.used['model'], executions=services.used['execution'], consecutive_no_gain=no_gain, consecutive_failures=failures, elapsed_seconds=time.monotonic() - started)
            value = await run_stage(services, 'stop', lambda: workflow.stop_policy.decide(state), validator=stop_reason)
            if value:
                services.record('stop-decision', reason=stop_reason(value), phase='round', evidence_ids=list(value.evidence_ids) if isinstance(value, StopDecision) else [])
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
            await services.emit('before_run', {'baseline_id': baseline.snapshot_id})
            result = await evaluate(baseline)
            if not result.complete and (not any((t.record is not None and diagnostic_reference(t.record, self.context.artifacts) for t in result.trials))):
                reason = 'reference_unavailable'
            else:
                provisional = result
                reason = await SearchEngine().run(schedule, baseline, SearchProblem(begin, propose, probe, compose, select, stop, advance, services.record, state=state, services=services, managed=True))
                await services.emit('before_finalization')
                if not final_compared:
                    await run_stage(services, 'select', lambda: promote(final=True), bounded=False)
        except AllocationExhausted:
            reason = 'budget_exhausted'
            await services.emit('before_finalization')
            try:
                await run_stage(services, 'select', lambda: promote(final=True), bounded=False)
            except AllocationExhausted:
                pass
        except AssessmentUnavailable:
            reason = 'assessment_unavailable'
        except StageFailure as exc:
            reason = 'stage_failed.' + exc.failure.stage
        finally:
            final_budget.close()
        await services.emit('before_finalization')
        return TaskSetOutcome(plan, self.snapshot, official, official_harness, tuple(candidates), tuple(evaluator.evaluations), decision, reason, tuple(exploration))
