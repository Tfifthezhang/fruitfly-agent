"""One evidence-driven workflow; generators and execution are injected ports."""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from dataclasses import replace
import time
import inspect

from ..contracts.pipeline import (CandidateBundle, CompositionRequest, HarnessSnapshot,
    ImprovementOutcome, ProposalRequest, SelectionDecision, ExecutionRecord, Measurement)


from .budget import BudgetScope, AllocationExhausted, operation_deadline
from .stopping import BoundedStopPolicy, SearchState


class WorkflowServices:
    """Job-local accounting and cancellation. Editor receives a restricted view."""
    def __init__(self, plan, *, edit=None, complete=None, record=None, signal=None, budget=None):
        self.plan, self.editor = plan, edit
        self.completer = complete
        self.sink = record or (lambda event, **fields: None)
        self.budget = budget or BudgetScope({'model': plan.max_model_calls, 'execution': plan.max_executions}, signal=signal)
        self.signal = self.budget.signal
        self.used = self.budget.used
        self.events = []
        self.resources = []
        self.verification_budget = None

    def own(self, resource):
        if all(item is not resource for item in self.resources):
            self.resources.append(resource)
        return resource

    async def close(self):
        """Close owned optional async resources, even after cancellation."""
        resources, self.resources = self.resources, []
        for resource in reversed(resources):
            close = getattr(resource, 'aclose', None)
            if close is not None:
                try:
                    await asyncio.wait_for(close(), timeout=min(self.plan.operation_timeout, 10))
                except Exception as exc:
                    self.record('cleanup-failed', resource=type(resource).__qualname__, error=type(exc).__name__)
        self.budget.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *error):
        await self.close()

    def check(self):
        self.budget.check()

    def reserve(self, kind, amount=1):
        self.budget.reserve(kind, amount)

    @contextmanager
    def phase(self, budget):
        previous = self.budget
        self.budget = budget
        try:
            yield
        finally:
            self.budget = previous

    def protect_verification(self, limits):
        self.verification_budget = self.budget.child(limits)

    def record(self, event, **fields):
        self.events.append((event, fields))
        self.sink(event, **fields)

    async def edit(self, stage, request):
        self.check()
        if self.editor is None:
            raise ValueError('this generator requires an editor capability')
        return await self.editor(stage, request, self)

    async def complete(self, system, prompt):
        if self.completer is None:
            raise ValueError('this generator requires a model completion capability')
        self.reserve('model')
        self.record('generator-model-request')
        result = await self.operation(self.completer(system, prompt, signal=self.signal))
        self.record('generator-model-response', text=result)
        return result

    async def operation(self, awaitable):
        try:
            self.check()
        except BaseException:
            if inspect.iscoroutine(awaitable):
                awaitable.close()
            raise
        deadline = min(time.monotonic() + self.plan.operation_timeout,
                       self.budget.deadline or float('inf'), operation_deadline.get() or float('inf'))
        token = operation_deadline.set(deadline)
        try:
            work = asyncio.ensure_future(awaitable)
        finally:
            operation_deadline.reset(token)
        cancelled = asyncio.create_task(self.signal.wait())
        try:
            timeout = max(0, deadline - time.monotonic())
            done, _ = await asyncio.wait((work, cancelled), timeout=timeout,
                                         return_when=asyncio.FIRST_COMPLETED)
            self.check()
            if work not in done:
                raise TimeoutError('improvement operation timed out')
            return await work
        finally:
            work.cancel()
            cancelled.cancel()
            await asyncio.gather(work, cancelled, return_exceptions=True)


class GeneratorServices:
    """A generator may edit and record; it cannot execute, verify or activate."""
    def __init__(self, services):
        self.services = services

    def check(self):
        self.services.check()

    def record(self, event, **fields):
        self.services.record(event, **fields)

    async def edit(self, stage, request):
        if stage not in {'propose', 'compose'}:
            raise ValueError('candidate editing stage is required')
        return await self.services.edit(stage, request)

    async def complete(self, system, prompt):
        return await self.services.complete(system, prompt)


class AgentGenerator:
    generator_id = 'agent-editor-v1'
    required_capabilities = frozenset({'editor'})

    async def propose(self, request, services):
        from ..contracts.pipeline import ProposalResult
        candidate = await services.edit('propose', request)
        return ProposalResult((candidate,))


class AgentComposer:
    async def compose(self, request, services):
        return await services.edit('compose', request)


class GeneratorRegistry:
    """Register factories; each job receives its own generator state."""
    def __init__(self):
        self.factories = {}
        self.metadata = {}

    def register(self, generator_id, factory, *, implementation_id=None, label=None, required_capabilities=None):
        from ..contracts.pipeline import identifier, GeneratorDefinition
        identifier(generator_id)
        if generator_id in self.factories or not callable(factory):
            raise ValueError('invalid or duplicate generator registration')
        self.factories[generator_id] = factory
        self.metadata[generator_id] = GeneratorDefinition(generator_id,
            implementation_id or getattr(factory, 'implementation_id', generator_id),
            label or getattr(factory, 'label', generator_id),
            getattr(factory, 'required_capabilities', frozenset()) if required_capabilities is None else required_capabilities)

    def definitions(self):
        return tuple(self.metadata[name] for name in sorted(self.metadata))

    def create(self, generator_id):
        if generator_id not in self.factories:
            raise ValueError('unknown candidate generator: ' + generator_id)
        generator = self.factories[generator_id]()
        if generator.generator_id != generator_id:
            raise ValueError('generator identity differs from its registration')
        if generator.required_capabilities != self.metadata[generator_id].required_capabilities:
            raise ValueError('generator capability requirements differ from its declaration')
        return generator


class ImprovementWorkflow:
    """Propose, execute, compose, select and reflect without implicit activation.

    The caller freezes experience once per task. Returned entries are pending;
    only a host can commit them or activate a persistent candidate.
    """
    def __init__(self, *, generators, components, runner, composer, selector,
                 reflector=None, measurements=None, verifier=None, stop_policy=None):
        self.generators, self.components, self.runner = generators, components, runner
        self.composer, self.selector, self.reflector = composer, selector, reflector
        self.measurements, self.verifier = measurements, verifier
        self.stop_policy = stop_policy or BoundedStopPolicy()

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
        from ..contracts.pipeline import ProposalResult
        if services.plan != plan:
            raise ValueError('workflow services belong to another plan')
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
        seen = {baseline.snapshot_id}

        async def execute(harness):
            # Composite runners charge their leaf task executions themselves.
            services.reserve('execution', getattr(self.runner, 'execution_charge', 1))
            services.record('execution-start', harness_id=harness.snapshot_id, task_id=task.task_id)
            record = await services.operation(self.runner.execute(plan, task, harness))
            if (record.task_id != task.task_id or record.material_id != task.material_id
                    or record.harness_id != harness.snapshot_id or record.initial_state_id != plan.parent.state
                    or record.conditions_id != plan.conditions_id or any(r.run_id == record.run_id for r in records)):
                raise ValueError('execution receipt differs from frozen task, state, conditions or harness')
            records.append(record)
            harnesses[harness.snapshot_id] = harness
            services.record('execution-finished', run_id=record.run_id, status=record.status)
            if plan.feedback == 'scored' and record.status == 'completed':
                measurement = await services.operation(self.measurements.measure(task, record))
                if measurement is not None:
                    if measurement.run_id != record.run_id:
                        raise ValueError('measurement belongs to another execution')
                    feedback.append(measurement)
            return record

        async def choose():
            nonlocal decision, selected
            selectable = tuple(r for r in records if r.status == 'completed')
            if not selectable:
                return
            measured = {m.run_id: m for m in feedback}
            if plan.feedback == 'scored':
                # Missing measurements never remove the known baseline from comparison.
                if any(r.run_id not in measured for r in selectable):
                    services.record('selection-insufficient', reason='missing measurements; incumbent retained')
                    return
                utility = -1 if getattr(self.measurements, 'direction', 'max') == 'min' else 1
                # Stable max keeps the baseline on a tie.
                best = max(selectable, key=lambda r: utility * measured[r.run_id].score)
                value = SelectionDecision(best.run_id, 'Best measured development result; ties retain earlier result')
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

        try:
            for _ in range(plan.width):
                record = await execute(baseline)
                if selected is None and record.status == 'completed':
                    selected = record
                    decision = SelectionDecision(record.run_id, 'Baseline retained until supported comparison')
            if selected is None:
                reason = 'reference_unavailable'
            else:
                # Protect final selection from exploratory editor/tool requests.
                selection_budget = services.budget.child({
                    'model': min(8, services.budget.available('model') // 8), 'execution': 0})
                history: tuple[CandidateBundle, ...] = ()
                rounds = plan.depth if plan.mode == 'sequential' else 1
                for round_index in range(rounds):
                    reference_records = tuple(records)
                    prior_candidates = tuple(candidates)
                    pool = []
                    stop = False
                    width = plan.width if plan.mode == 'parallel' else 1
                    for index in range(width):
                        for scope in ('invariant', 'domain'):
                            request = ProposalRequest(plan, task, current, reference_records, scope,
                                index, tuple(experience), tuple(feedback), prior_candidates)
                            services.record('proposal-start', scope=scope, index=index, round=round_index)
                            proposal = await services.operation(generator.propose(request, restricted))
                            if not isinstance(proposal, ProposalResult):
                                raise TypeError('generator must return ProposalResult')
                            for candidate in proposal.candidates:
                                self.validate(candidate, plan=plan, baseline=current, records=reference_records)
                                candidates.append(candidate)
                                pool.append(candidate)
                            stop = stop or proposal.stop
                            services.record('proposal-finished', scope=scope, index=index,
                                            candidate_ids=[c.candidate_id for c in proposal.candidates])
                    repeated = bool(pool) and all(c.harness.snapshot_id in seen for c in pool)
                    for candidate in pool:
                        await execute(candidate.harness)
                        seen.add(candidate.harness.snapshot_id)
                    if not pool:
                        reason = self.stop_policy.decide(SearchState(round_index, rounds, 0, False, stop)) or 'no_candidate'
                        break
                    compositions = []
                    for index in range(width):
                        composition = CompositionRequest(plan, task, current, (*history, *pool),
                            tuple(records), index, tuple(experience), tuple(feedback))
                        candidate = await services.operation(self.composer.compose(composition, restricted))
                        self.validate(candidate, plan=plan, baseline=current, records=tuple(records))
                        candidates.append(candidate)
                        compositions.append(candidate)
                        await execute(candidate.harness)
                    history = (*history, *pool, *compositions)
                    services.record('round-completed', index=round_index)
                    reason = self.stop_policy.decide(SearchState(round_index, rounds, len(pool), repeated, stop,
                        tuple(feedback), selected.run_id if selected else None, services.used['model'], services.used['execution']))
                    if reason:
                        break
                    if plan.mode == 'sequential':
                        await choose()
                        current = harnesses[selected.harness_id]
        except AllocationExhausted:
            reason = 'budget_exhausted'
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
                                     tuple(records), decision, stop_reason=reason or 'completed')
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
        if self.reflector is not None and selected is not None:
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


__all__ = ['ImprovementWorkflow', 'WorkflowServices', 'GeneratorRegistry',
           'AgentGenerator', 'AgentComposer', 'AllocationExhausted']
