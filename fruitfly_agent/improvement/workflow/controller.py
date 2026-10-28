"""One evidence-driven workflow; generators and execution are injected ports."""
from __future__ import annotations
import asyncio
from dataclasses import asdict, replace
import time
from uuid import uuid4
from fruitfly_agent.improvement.contracts.pipeline import CandidateBundle, CompositionRequest, HarnessSnapshot, ImprovementOutcome, ProposalRequest, SelectionDecision, ExecutionRecord, Measurement
from fruitfly_agent.improvement.workflow.budget import AllocationExhausted
from fruitfly_agent.improvement.contracts.stopping import SearchState
from fruitfly_agent.improvement.workflow.services import GeneratorServices
from fruitfly_agent.improvement.contracts.stopping import StopDecision, stop_reason
from fruitfly_agent.improvement.contracts.assessment import AssessmentUnavailable
from fruitfly_agent.improvement.execution.facts import ensure_facts
from fruitfly_agent.improvement.execution.scheduler import TaskScheduler
from fruitfly_agent.improvement.workflow.engine import SearchEngine
from fruitfly_agent.improvement.workflow.problems import SearchProblem
from .operations import run_stage, diagnostic_reference, require_type, validate_assessment_result
from .state import WorkflowState
from ..contracts.search import ExplorationDecision
from ..contracts.failures import IntegrityError, StageFailure, Failure
from ..execution.facts import attach_facts, receipt_facts

class ImprovementWorkflow:
    """Propose, execute, compose, select and reflect without implicit activation.

    The caller freezes experience once per task. Returned entries are pending;
    only a host can commit them or activate a persistent candidate.
    """

    def __init__(self, *, generators, components, runner, composer, selector, reflector=None, measurements=None, verifier=None, stop_policy=None, strategies=None, artifacts=None, completed_assessment=None, exploration=None, problem=None, selection=None):
        self.generators, self.components, self.runner = (generators, components, runner)
        self.composer, self.selector, self.reflector = (composer, selector, reflector)
        self.measurements, self.verifier = (measurements, verifier)
        self.stop_policy = stop_policy
        self.selection = selection
        if selection is None:
            raise ValueError('improvement requires an injected selection policy')
        if strategies is None:
            raise ValueError('improvement requires an injected strategy registry')
        self.strategies = strategies
        self.artifacts, self.completed_assessment = (artifacts, completed_assessment)
        self.exploration = exploration
        self.problem = problem
        if not callable(getattr(self.stop_policy, 'decide', None)):
            raise ValueError('stop policy must implement decide')

    def validate(self, candidate, *, plan, baseline, records):
        if not isinstance(candidate, CandidateBundle) or candidate.parent != plan.parent or candidate.base != baseline:
            raise ValueError('candidate must match its frozen parent and editing baseline')
        if set(candidate.changed_ids) - set(plan.component_ids):
            raise ValueError('candidate changed an undeclared component')
        allowed_evidence = {r.run_id for r in records}
        changed = set(candidate.changed_ids)
        covered = set()
        for reason in candidate.reasons:
            if reason.component_id not in changed or set(reason.evidence_ids) - allowed_evidence:
                raise ValueError('edit attribution is outside the supplied execution evidence')
            covered.add(reason.component_id)
        if changed - covered:
            raise ValueError('each changed component needs execution evidence')
        self.components.validate(candidate.harness)

    async def run(self, plan, task, baseline, services, *, experience=()):
        outcome = await self._run(plan, task, baseline, services, experience=experience)
        if services.state is not None:
            services.state.phase = 'finished'
        try:
            await services.emit('before_run_end', {'stop_reason': outcome.stop_reason})
        except StageFailure:
            return replace(outcome, decision=None, stop_reason='stage_failed.hook')
        return outcome

    async def _run(self, plan, task, baseline, services, *, experience=()):
        self.components.configure(plan.component_options)
        if self.problem is not None:
            return await self.problem.run(self, plan, task, baseline, services, experience=experience)
        from fruitfly_agent.improvement.contracts.pipeline import ProposalResult
        if services.plan != plan:
            raise ValueError('workflow services belong to another plan')
        schedule = self.strategies.get(plan.strategy_id).schedule(plan)
        self.components.validate(baseline)
        if set(plan.component_ids) - {c.component_id for c in baseline.components}:
            raise ValueError('plan contains an unregistered component')
        if plan.purpose == 'persistent' and self.verifier is None:
            raise ValueError('persistent improvement requires an explicit verification policy')
        if any((baseline.component(v).role == 'I' for v in plan.component_ids)):
            if 'improver-comparison' not in self.runner.capabilities:
                raise ValueError('I edits require an improver comparison runner')
        for component_id in plan.component_ids:
            required: frozenset[str] = getattr(self.components.adapters[component_id], 'required_capabilities', frozenset())
            if required - self.runner.capabilities:
                raise ValueError('runner lacks declared component capabilities')
        generator = services.own(self.generators.create(plan.generator_id))
        available = {'editor'} if services.editor is not None else set()
        if services.completer is not None:
            available.add('model')
        if plan.feedback == 'scored':
            if self.measurements is None:
                raise ValueError('scored generation requires a measurement capability')
            available.add('measurements')
        if generator.required_capabilities - available:
            raise ValueError('candidate generator lacks required capabilities')
        restricted = GeneratorServices(services)
        state = services.state = WorkflowState(baseline)
        state.records = []
        state.candidates = []
        state.feedback = []
        state.harnesses = {baseline.snapshot_id: baseline}
        current, reason = (baseline, 'completed')
        state.decision = state.selected = None
        selection_budget = None
        state.selection_count = -1
        state.no_gain = 0
        state.failures = 0
        state.assessments = []
        state.exploration_decisions = []
        started = time.monotonic()
        scheduler = services.own(TaskScheduler(1))

        def checkpoint():
            harness = state.harnesses[state.selected.harness_id] if state.selected else baseline
            value = ImprovementOutcome(plan, task, state.selected, harness, tuple(state.candidates), tuple(state.records), state.decision, stop_reason='in_progress', exploration=tuple(state.exploration_decisions))
            services.record('workflow-checkpoint', outcome=asdict(value))

        async def execute(harness):
            services.reserve('execution', getattr(self.runner, 'execution_charge', 1))
            services.record('execution-start', harness_id=harness.snapshot_id, task_id=task.task_id)
            await services.emit('before_trial', {'harness_id': harness.snapshot_id, 'task_id': task.task_id})
            try:
                record = (await scheduler.map((lambda: run_stage(services, 'execute', lambda: self.runner.execute(plan, task, harness), validator=lambda v: require_type(v, ExecutionRecord)),)))[0]
            except StageFailure as exc:
                record = exc.record or ExecutionRecord('failed-' + uuid4().hex, task.task_id, task.material_id, harness.snapshot_id, plan.parent.state, plan.conditions_id, 'error', 'Execution ended without a complete receipt: ' + exc.failure.code)
                if self.artifacts is not None and exc.record is None:
                    record = attach_facts(record, receipt_facts(record, self.artifacts, termination_reason='execution_' + exc.failure.code), self.artifacts)
            if record.task_id != task.task_id or record.material_id != task.material_id or record.harness_id != harness.snapshot_id or (record.initial_state_id != plan.parent.state) or (record.conditions_id != plan.conditions_id) or any((r.run_id == record.run_id for r in state.records)):
                raise IntegrityError('execution receipt differs from frozen task, state, conditions or harness')
            if self.artifacts is not None:
                record = ensure_facts(record, self.artifacts)
            state.records.append(record)
            state.failures = 0 if record.status == 'completed' else state.failures + 1
            state.harnesses[harness.snapshot_id] = harness
            if state.selected is None and record.status == 'completed':
                state.selected = record
                state.decision = SelectionDecision(record.run_id, 'First completed execution retained until supported comparison')
            services.record('execution-finished', run_id=record.run_id, status=record.status)
            services.record('execution-receipt', receipt=asdict(record))
            checkpoint()
            await services.emit('after_trial', {'receipt': asdict(record)})
            if plan.feedback == 'scored' and record.status == 'completed':
                try:
                    measurement = await run_stage(services, 'measure', lambda: self.measurements.measure(task, record), validator=lambda v: require_type(v, Measurement, optional=True))
                except StageFailure:
                    measurement = None
                if measurement is not None:
                    if measurement.run_id != record.run_id:
                        raise IntegrityError('measurement belongs to another execution')
                    state.feedback.append(measurement)
            if self.completed_assessment is not None:
                record, values = await run_stage(services, 'assess', lambda: self.completed_assessment.assess(task, record),
                    validator=lambda value: validate_assessment_result(value, record))
                state.records[-1] = record
                state.assessments.extend(values)
            return record

        async def choose():
            if state.selection_count == len(state.records):
                return
            selectable = tuple((r for r in state.records if r.status == 'completed'))
            if not selectable:
                return
            value = await run_stage(services, 'select', lambda: self.selection.choose(plan, task, selectable, tuple(state.feedback), selector=self.selector, measurements=self.measurements), validator=lambda v: require_type(v, SelectionDecision, optional=True))
            if value is None:
                services.record('selection-insufficient', reason='selection unavailable; incumbent retained')
                return
            if value.assurance != 'selected':
                raise IntegrityError('output selection cannot claim independent verification')
            chosen = next((r for r in selectable if r.run_id == value.run_id), None)
            if chosen is None:
                raise IntegrityError('selector must choose an existing completed execution')
            state.decision, state.selected = (value, chosen)
            state.selection_count = len(state.records)
            checkpoint()

        async def decide_stop(snapshot):
            value = await run_stage(services, 'stop', lambda: self.stop_policy.decide(snapshot), validator=stop_reason)
            if value is not None:
                services.record('stop-decision', reason=stop_reason(value), phase=snapshot.phase, evidence_ids=list(value.evidence_ids) if isinstance(value, StopDecision) else [])
            return stop_reason(value)
        try:
            await services.emit('before_run', {'baseline_id': baseline.snapshot_id})
            for _ in range(schedule.references):
                record = await execute(baseline)
                if state.selected is None and record.status == 'completed':
                    state.selected = record
                    state.decision = SelectionDecision(record.run_id, 'Baseline retained until supported comparison')
                    checkpoint()
                if self.completed_assessment is not None:
                    await run_stage(services, 'assess', lambda: self.completed_assessment.ensure_available())
            if not any((diagnostic_reference(r, self.artifacts) for r in state.records)):
                reason = 'reference_unavailable'
            else:
                selection_budget = services.budget.child({'model': min(8, services.budget.available('model') // 8), 'execution': 0})
                reference_records: tuple[ExecutionRecord, ...] = ()
                prior_candidates: tuple[CandidateBundle, ...] = ()

                async def begin(round_index, current):
                    nonlocal reference_records, prior_candidates
                    reference_records, prior_candidates = (tuple(state.records), tuple(state.candidates))

                async def propose(current, scope, index):
                    request = ProposalRequest(plan, task, current, reference_records, scope, index, tuple(experience), tuple(state.feedback), prior_candidates)
                    contribution = await services.emit('before_proposal', {'harness_id': current.snapshot_id})
                    request = replace(request, context=contribution.resources)
                    proposal = await run_stage(services, 'propose', lambda: generator.propose(request, restricted))
                    if not isinstance(proposal, ProposalResult):
                        raise StageFailure(Failure('propose', 'invalid_result', 'TypeError'))

                    async def validate_batch():
                        for candidate in proposal.candidates:
                            self.validate(candidate, plan=plan, baseline=current, records=reference_records)
                        return proposal
                    await run_stage(services, 'propose', lambda: validate_batch())
                    for candidate in proposal.candidates:
                        state.candidates.append(candidate)
                        services.record('candidate-validated', candidate=asdict(candidate))
                        await services.emit('after_candidate_validated', {'candidate_id': candidate.candidate_id, 'harness_id': candidate.harness.snapshot_id, 'reasons': [asdict(r) for r in candidate.reasons]})
                    return proposal

                async def probe(harness):
                    await execute(harness)
                    if self.completed_assessment is not None:
                        await run_stage(services, 'assess', lambda: self.completed_assessment.ensure_available())

                async def compose(current, history, index):
                    request = CompositionRequest(plan, task, current, history, tuple(state.records), index, tuple(experience), tuple(state.feedback))
                    candidate = await run_stage(services, 'compose', lambda: self.composer.compose(request, restricted))
                    await run_stage(services, 'compose', lambda: self.validate(candidate, plan=plan, baseline=current, records=tuple(state.records)))
                    state.candidates.append(candidate)
                    services.record('candidate-validated', candidate=asdict(candidate))
                    await services.emit('after_candidate_validated', {'candidate_id': candidate.candidate_id, 'harness_id': candidate.harness.snapshot_id, 'reasons': [asdict(r) for r in candidate.reasons]})
                    return candidate

                async def select(round_index, last):
                    nonlocal selection_budget
                    previous = state.selected.harness_id if state.selected else None
                    if last and selection_budget is not None:
                        selection_budget.close()
                        selection_budget = None
                    await choose()
                    state.no_gain = state.no_gain + 1 if state.selected is None or state.selected.harness_id == previous else 0

                async def stop(round_index, count, repeated, requested):
                    return await decide_stop(SearchState(round_index, schedule.rounds, count, repeated, requested, tuple(state.feedback), state.selected.run_id if state.selected else None, services.used['model'], services.used['execution'], consecutive_no_gain=state.no_gain, consecutive_failures=state.failures, assessments=tuple(state.assessments), elapsed_seconds=time.monotonic() - started))

                async def advance(current):
                    if state.selected is None or self.exploration is None:
                        return current
                    seed = await run_stage(services, 'explore', lambda: self.exploration.choose(task, tuple(state.records), state.selected, self.completed_assessment), validator=lambda v: require_type(v, ExplorationDecision))
                    chosen_seed = next((r for r in state.records if r.run_id == seed.run_id and r.status == 'completed'), None)
                    if chosen_seed is None:
                        raise IntegrityError('exploration must choose an existing completed execution')
                    state.exploration_decisions.append(seed)
                    services.record('exploration-selected', **asdict(seed))
                    return state.harnesses[chosen_seed.harness_id]
                reason = await SearchEngine().run(schedule, baseline, SearchProblem(begin, propose, probe, compose, select, stop, advance, services.record, state=state, services=services, managed=True))
        except AllocationExhausted:
            reason = 'budget_exhausted'
        except AssessmentUnavailable:
            reason = 'assessment_unavailable'
        except StageFailure as exc:
            reason = 'stage_failed.' + exc.failure.stage
        state.phase = 'finalizing'
        try:
            await services.emit('before_finalization')
        except StageFailure:
            reason = 'stage_failed.hook'
        if state.selected is not None:
            try:
                if selection_budget is not None:
                    selection_budget.close()
                await choose()
            except AllocationExhausted:
                services.record('selection-insufficient', reason='budget exhausted; incumbent retained')
                reason = 'budget_exhausted'
            except StageFailure:
                services.record('selection-insufficient', reason='selection stage failed; incumbent retained')
        services.check()
        chosen_harness = state.harnesses[state.selected.harness_id] if state.selected else baseline
        outcome = ImprovementOutcome(plan, task, state.selected, chosen_harness, tuple(state.candidates), tuple(state.records), state.decision, stop_reason=reason or 'completed', exploration=tuple(state.exploration_decisions))
        if reason in {'assessment_unavailable', 'stage_failed.hook'}:
            return outcome
        if plan.purpose == 'persistent' and state.selected is not None:
            protected = services.verification_budget
            if protected is not None:
                protected.extend({k: services.budget.available(k) for k in ('model', 'execution')})
            try:
                with services.phase(protected or services.budget):
                    proof = await run_stage(services, 'verify', lambda: self.verifier.verify(outcome), validator=lambda v: require_type(v, SelectionDecision, optional=True))
            except AllocationExhausted:
                return replace(outcome, decision=None, stop_reason='budget_exhausted')
            except StageFailure:
                return replace(outcome, decision=None, stop_reason='verification_failed')
            finally:
                if protected is not None:
                    protected.close()
            if proof is None or proof.assurance != 'verified' or proof.run_id != state.selected.run_id:
                return replace(outcome, decision=None, stop_reason='verification_failed')
            outcome = replace(outcome, decision=proof)
        if plan.retain_experience and self.reflector is not None and (state.selected is not None):
            try:
                entries = await services.operation(self.reflector.reflect(outcome))
                known = {r.run_id for r in state.records}
                for entry in entries:
                    if entry.task_id != task.task_id or entry.harness != outcome.harness or set(entry.evidence_ids) - known:
                        raise ValueError('experience must cite this task and its executed contrasts')
                outcome = replace(outcome, experience=tuple(entries))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                services.record('reflection-failed', error=type(exc).__name__)
        services.check()
        return outcome
