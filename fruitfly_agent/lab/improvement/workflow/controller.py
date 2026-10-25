"""One evidence-driven workflow; generators and execution are injected ports."""
from __future__ import annotations

import asyncio
from dataclasses import asdict, replace
import time

from ..contracts.pipeline import (CandidateBundle, CompositionRequest, HarnessSnapshot,
    ImprovementOutcome, ProposalRequest, SelectionDecision, ExecutionRecord, Measurement)


from .budget import AllocationExhausted
from .stopping import BoundedStopPolicy, SearchState


from .services import GeneratorServices
from ..contracts.stopping import StopDecision, stop_reason
from ..strategies import builtin_strategies
from ..contracts.assessment import AssessmentUnavailable
from ..execution.facts import ensure_facts
from ..strategies.exploration import IncumbentExploration
from ..assessment.selection import measured_selection
from ..execution.scheduler import TaskScheduler
from .engine import SearchEngine
from .problems import SearchProblem

class ImprovementWorkflow:
    """Propose, execute, compose, select and reflect without implicit activation.

    The caller freezes experience once per task. Returned entries are pending;
    only a host can commit them or activate a persistent candidate.
    """
    def __init__(self, *, generators, components, runner, composer, selector,
                 reflector=None, measurements=None, verifier=None, stop_policy=None, strategies=None,
                 artifacts=None, completed_assessment=None, exploration=None, problem=None):
        self.generators, self.components, self.runner = generators, components, runner
        self.composer, self.selector, self.reflector = composer, selector, reflector
        self.measurements, self.verifier = measurements, verifier
        self.stop_policy = stop_policy or BoundedStopPolicy()
        self.strategies = strategies or builtin_strategies()
        self.artifacts, self.completed_assessment = artifacts, completed_assessment
        self.exploration = exploration or IncumbentExploration()
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
        self.components.configure(plan.component_options)
        if self.problem is not None:
            return await self.problem.run(self, plan, task, baseline, services, experience=experience)
        from ..contracts.pipeline import ProposalResult
        if services.plan != plan:
            raise ValueError('workflow services belong to another plan')
        schedule = self.strategies.get(plan.strategy_id).schedule(plan)
        self.components.validate(baseline)
        if set(plan.component_ids) - {c.component_id for c in baseline.components}:
            raise ValueError('plan contains an unregistered component')
        if plan.purpose == 'persistent' and self.verifier is None:
            raise ValueError('persistent improvement requires an explicit verification policy')
        if any(baseline.component(v).role == 'I' for v in plan.component_ids):
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
        records: list[ExecutionRecord] = []
        candidates: list[CandidateBundle] = []
        feedback: list[Measurement] = []
        harnesses = {baseline.snapshot_id: baseline}
        current, reason = baseline, 'completed'
        decision = selected = None
        selection_budget = None
        selection_count = -1
        no_gain = 0
        failures = 0
        assessments = []
        exploration_decisions = []
        started = time.monotonic()
        scheduler = services.own(TaskScheduler(1))

        async def execute(harness):
            nonlocal failures
            # Composite runners charge their leaf task executions themselves.
            services.reserve('execution', getattr(self.runner, 'execution_charge', 1))
            services.record('execution-start', harness_id=harness.snapshot_id, task_id=task.task_id)
            record = (await scheduler.map((lambda: services.operation(self.runner.execute(plan, task, harness)),)))[0]
            if (record.task_id != task.task_id or record.material_id != task.material_id
                    or record.harness_id != harness.snapshot_id or record.initial_state_id != plan.parent.state
                    or record.conditions_id != plan.conditions_id or any(r.run_id == record.run_id for r in records)):
                raise ValueError('execution receipt differs from frozen task, state, conditions or harness')
            if self.artifacts is not None:
                record = ensure_facts(record, self.artifacts)
            records.append(record)
            failures = 0 if record.status == 'completed' else failures + 1
            harnesses[harness.snapshot_id] = harness
            services.record('execution-finished', run_id=record.run_id, status=record.status)
            if plan.feedback == 'scored' and record.status == 'completed':
                measurement = await services.operation(self.measurements.measure(task, record))
                if measurement is not None:
                    if measurement.run_id != record.run_id:
                        raise ValueError('measurement belongs to another execution')
                    feedback.append(measurement)
            if self.completed_assessment is not None:
                record, values = await self.completed_assessment.assess(task, record)
                records[-1] = record
                assessments.extend(values)
            return record

        async def choose():
            nonlocal decision, selected, selection_count
            if selection_count == len(records):
                return
            selectable = tuple(r for r in records if r.status == 'completed')
            if not selectable:
                return
            if plan.feedback == 'scored':
                # Missing measurements never remove the known baseline from comparison.
                value = measured_selection(selectable, feedback, direction=getattr(self.measurements, 'direction', 'max'))
                if value is None:
                    services.record('selection-insufficient', reason='missing measurements; incumbent retained')
                    return
            elif len(selectable) == 1:
                value = SelectionDecision(selectable[0].run_id, 'Only available executed result')
            else:
                value = await services.operation(self.selector.select(task, selectable))
            if value.assurance != 'selected':
                raise ValueError('output selection cannot claim independent verification')
            chosen = next((r for r in selectable if r.run_id == value.run_id), None)
            if chosen is None:
                raise ValueError('selector must choose an existing completed execution')
            decision, selected = value, chosen
            selection_count = len(records)

        def decide_stop(state):
            value = self.stop_policy.decide(state)
            if value is not None:
                services.record('stop-decision', reason=stop_reason(value), phase=state.phase,
                    evidence_ids=list(value.evidence_ids) if isinstance(value, StopDecision) else [])
            return stop_reason(value)

        try:
            for _ in range(schedule.references):
                record = await execute(baseline)
                if selected is None and record.status == 'completed':
                    selected = record
                    decision = SelectionDecision(record.run_id, 'Baseline retained until supported comparison')
                if self.completed_assessment is not None:
                    self.completed_assessment.ensure_available()
            if selected is None:
                reason = 'reference_unavailable'
            else:
                # Protect final selection from exploratory editor/tool requests.
                selection_budget = services.budget.child({
                    'model': min(8, services.budget.available('model') // 8), 'execution': 0})
                reference_records: tuple[ExecutionRecord, ...] = ()
                prior_candidates: tuple[CandidateBundle, ...] = ()

                async def begin(round_index, current):
                    nonlocal reference_records, prior_candidates
                    reference_records, prior_candidates = tuple(records), tuple(candidates)

                async def propose(current, scope, index):
                    request = ProposalRequest(plan, task, current, reference_records, scope,
                        index, tuple(experience), tuple(feedback), prior_candidates)
                    proposal = await services.operation(generator.propose(request, restricted))
                    if not isinstance(proposal, ProposalResult):
                        raise TypeError('generator must return ProposalResult')
                    for candidate in proposal.candidates:
                        self.validate(candidate, plan=plan, baseline=current, records=reference_records)
                        candidates.append(candidate)
                    return proposal

                async def probe(harness):
                    await execute(harness)
                    if self.completed_assessment is not None:
                        self.completed_assessment.ensure_available()

                async def compose(current, history, index):
                    request = CompositionRequest(plan, task, current, history,
                        tuple(records), index, tuple(experience), tuple(feedback))
                    candidate = await services.operation(self.composer.compose(request, restricted))
                    self.validate(candidate, plan=plan, baseline=current, records=tuple(records))
                    candidates.append(candidate)
                    return candidate

                async def select(round_index, last):
                    nonlocal no_gain, selection_budget
                    previous = selected.harness_id if selected else None
                    if last and selection_budget is not None:
                        selection_budget.close()
                        selection_budget = None
                    await choose()
                    no_gain = no_gain + 1 if selected is None or selected.harness_id == previous else 0

                def stop(round_index, count, repeated, requested):
                    return decide_stop(SearchState(round_index, schedule.rounds, count, repeated, requested,
                        tuple(feedback), selected.run_id if selected else None, services.used['model'], services.used['execution'],
                        consecutive_no_gain=no_gain, consecutive_failures=failures,
                        assessments=tuple(assessments), elapsed_seconds=time.monotonic() - started))

                async def advance(current):
                    seed = await services.operation(self.exploration.choose(
                        task, tuple(records), selected, self.completed_assessment))
                    chosen_seed = next((r for r in records if r.run_id == seed.run_id and r.status == 'completed'), None)
                    if chosen_seed is None:
                        raise ValueError('exploration must choose an existing completed execution')
                    exploration_decisions.append(seed)
                    services.record('exploration-selected', **asdict(seed))
                    return harnesses[chosen_seed.harness_id]

                reason = await SearchEngine().run(schedule, baseline, SearchProblem(
                    begin, propose, probe, compose, select, stop, advance, services.record))
        except AllocationExhausted:
            reason = 'budget_exhausted'
        except AssessmentUnavailable:
            reason = 'assessment_unavailable'
        if selected is not None:
            try:
                if selection_budget is not None:
                    # Search has ended. Unused search allocation can supplement selection.
                    selection_budget.close()
                await choose()
            except AllocationExhausted:
                services.record('selection-insufficient', reason='budget exhausted; incumbent retained')
                reason = 'budget_exhausted'
        services.check()
        chosen_harness = harnesses[selected.harness_id] if selected else baseline
        outcome = ImprovementOutcome(plan, task, selected, chosen_harness, tuple(candidates),
                                     tuple(records), decision, stop_reason=reason or 'completed',
                                     exploration=tuple(exploration_decisions))
        if reason == 'assessment_unavailable':
            return outcome
        if plan.purpose == 'persistent' and selected is not None:
            protected = services.verification_budget
            if protected is not None:
                protected.extend({k: services.budget.available(k) for k in ('model', 'execution')})
            try:
                with services.phase(protected or services.budget):
                    proof = await services.operation(self.verifier.verify(outcome))
            except AllocationExhausted:
                return replace(outcome, decision=None, stop_reason='budget_exhausted')
            finally:
                if protected is not None:
                    protected.close()
            if proof is None or proof.assurance != 'verified' or proof.run_id != selected.run_id:
                return replace(outcome, decision=None, stop_reason='verification_failed')
            outcome = replace(outcome, decision=proof)
        if plan.retain_experience and self.reflector is not None and selected is not None:
            try:
                entries = await services.operation(self.reflector.reflect(outcome))
                known = {r.run_id for r in records}
                for entry in entries:
                    if (entry.task_id != task.task_id or entry.harness != outcome.harness
                            or set(entry.evidence_ids) - known):
                        raise ValueError('experience must cite this task and its executed contrasts')
                outcome = replace(outcome, experience=tuple(entries))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                services.record('reflection-failed', error=type(exc).__name__)
        services.check()
        return outcome

