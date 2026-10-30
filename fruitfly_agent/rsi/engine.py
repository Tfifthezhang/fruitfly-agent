"""Bounded resumable text evolution using the same host inbox as human improvement."""
from fruitfly_agent.improvement.contracts.failures import IntegrityError, CleanupError
from dataclasses import replace
import asyncio
import time
from .state import EvolutionController
from fruitfly_agent.improvement.contracts.versions import canonical_json, content_hash
from fruitfly_agent.improvement.contracts.stopping import policy_spec
from fruitfly_agent.improvement.workflow.budget import AllocationExhausted
from .contracts import EvolutionHost, EvolutionJob, VerificationEvidence, AdoptionResult
from fruitfly_agent.core.extensions.operations import OperationSupervisor


class EvolutionEngine:

    async def evolve(self, host: EvolutionHost, *, job_id: str, policy_id: str,
                     direction: str, max_steps: int = 2, phase_timeout_seconds: float = 60.0, signal=None,
                     continue_on_rejection=False, stop_policy=None, failure_handler=None) -> EvolutionJob:
        if not job_id or not policy_id or not direction.strip() or isinstance(max_steps, bool) or max_steps < 1:
            raise ValueError('job, policy, direction and a positive step budget are required')
        if type(continue_on_rejection) is not bool:
            raise ValueError('continue_on_rejection must be boolean')
        if stop_policy is not None and not callable(getattr(stop_policy, 'decide', None)):
            raise ValueError('stop policy must implement decide')
        budget = getattr(host, 'budget', None)
        strategy_id = content_hash(canonical_json({'continue_on_rejection': continue_on_rejection,
            'stop': policy_spec(stop_policy), 'allocation': dict(budget.limits) if budget is not None else None}))
        supervisor = OperationSupervisor(cleanup_error=CleanupError)
        controller = None
        def save(value):
            value = replace(value, schema_version=2, strategy_id=strategy_id)
            if budget is not None:
                value = replace(value, budget_state=budget.snapshot())
            if controller is not None:
                value = replace(value, elapsed_seconds=time.monotonic() - controller.started_at)
            host.save_job(value)
            return value
        def phase_timeout(value):
            return min(value.phase_timeout_seconds,
                max(0, budget.deadline - time.monotonic()) if budget is not None and budget.deadline is not None else float('inf'))
        job = host.load_job(job_id)
        if job is None:
            job = EvolutionJob(job_id, policy_id, direction, host.active_manifest(), max_steps, phase_timeout_seconds, strategy_id=strategy_id)
            job = save(job)
        elif (job.policy_id, job.direction, job.max_steps, job.phase_timeout_seconds) != (policy_id, direction, max_steps, phase_timeout_seconds):
            raise ValueError('persisted evolution job parameters differ')
        if job.strategy_id and job.strategy_id != strategy_id:
            raise ValueError('persisted evolution strategy differs')
        if budget is not None and job.steps and not job.budget_state:
            raise ValueError('existing evolution job has no root allocation evidence')
        if budget is not None and job.budget_state:
            budget.restore(job.budget_state)
        if signal is None and budget is not None:
            signal = budget.signal
        controller = EvolutionController(stop_policy, job.consecutive_no_gain, job.consecutive_failures,
            started_at=time.monotonic() - job.elapsed_seconds, budget=budget)
        if job.phase == 'activating':
            # Reconcile an interrupted commit; never blindly replay adoption.
            if host.is_active(job.candidate_id):
                job = replace(job, phase='ready', current_manifest=host.active_manifest(), candidate_id='', evidence=None)
            else:
                job = replace(job, phase='interrupted', stop_reason='activation_unconfirmed')
            job = save(job)
        elif job.phase in {'proposing', 'verifying'}:
            # Model/verification cost may already have been consumed before crash.
            if budget is not None:
                budget.forfeit()
            job = replace(job, phase='interrupted', stop_reason='interrupted_usage_unknown')
            job = save(job)
        if job.current_manifest != host.active_manifest():
            raise ValueError('evolution job active version is stale')
        while job.phase in {'ready', 'proposed', 'verified'} and job.steps <= job.max_steps:
            if signal is not None and signal.is_set():
                raise asyncio.CancelledError
            if job.phase == 'ready':
                if budget is not None:
                    try:
                        budget.check()
                    except TimeoutError:
                        job = save(replace(job, phase='complete', stop_reason='budget_deadline'))
                        break
                    if not budget.available('model') or not budget.available('execution'):
                        job = save(replace(job, phase='complete', stop_reason='budget_exhausted'))
                        break
                if job.steps == job.max_steps:
                    job = replace(job, phase='complete', stop_reason='step_limit')
                    job = save(job)
                    break
                job = replace(job, phase='proposing', steps=job.steps + 1)
                job = save(job)
                try:
                    candidate_id = await supervisor.run(lambda: host.propose(job.direction),
                        timeout=phase_timeout(job), signal=signal)
                except AllocationExhausted:
                    job = save(replace(job, phase='complete', stop_reason='budget_exhausted'))
                    break
                except Exception as exc:
                    if isinstance(exc, IntegrityError) or failure_handler is None or not failure_handler('proposal', exc):
                        raise
                    reason = controller.finish(steps=job.steps, limit=job.max_steps, outcome='proposal_failed')
                    job = save(replace(job, phase='complete' if reason else 'ready', stop_reason=reason or '',
                        consecutive_no_gain=controller.consecutive_no_gain, consecutive_failures=controller.consecutive_failures))
                    continue
                if candidate_id is None:
                    job = replace(job, phase='complete', stop_reason='no_candidate')
                    job = save(job)
                    break
                if not isinstance(candidate_id, str) or not candidate_id:
                    raise ValueError('proposal must identify a registered candidate')
                job = replace(job, phase='proposed', candidate_id=candidate_id)
                job = save(job)
            if job.phase == 'proposed':
                job = replace(job, phase='verifying')
                job = save(job)
                try:
                    evidence = await supervisor.run(lambda: host.verify(job.candidate_id, job.policy_id),
                        timeout=phase_timeout(job), signal=signal)
                except Exception as exc:
                    if isinstance(exc, IntegrityError) or failure_handler is None or not failure_handler('verification', exc):
                        raise
                    reason = controller.finish(steps=job.steps, limit=job.max_steps, outcome='verification_failed')
                    job = save(replace(job, phase='complete' if reason else 'ready', candidate_id='', evidence=None,
                        stop_reason=reason or '', consecutive_no_gain=controller.consecutive_no_gain,
                        consecutive_failures=controller.consecutive_failures))
                    continue
                if not isinstance(evidence, VerificationEvidence) or evidence.candidate_id != job.candidate_id or evidence.policy_id != job.policy_id or evidence.parent_manifest_digest != job.current_manifest:
                    raise ValueError('verification candidate, policy or parent mismatch')
                job = replace(job, phase='verified', evidence=evidence)
                job = save(job)
            if job.phase == 'verified':
                active_evidence = job.evidence
                if active_evidence is None:
                    raise ValueError('verified evolution phase lacks evidence')
                if signal is not None and signal.is_set():
                    raise asyncio.CancelledError
                if budget is not None:
                    try:
                        budget.check()
                    except TimeoutError:
                        job = save(replace(job, phase='complete', stop_reason='budget_deadline'))
                        break
                if not active_evidence.passed:
                    reason = controller.finish(steps=job.steps, limit=job.max_steps, outcome='rejected')
                    job = replace(job, phase='ready' if continue_on_rejection and not reason else ('complete' if reason else 'rejected'),
                        candidate_id='' if continue_on_rejection else job.candidate_id, evidence=None if continue_on_rejection else job.evidence,
                        stop_reason=reason or ('' if continue_on_rejection else 'verification_rejected'),
                        consecutive_no_gain=controller.consecutive_no_gain, consecutive_failures=controller.consecutive_failures)
                    job = save(job)
                    if job.phase == 'ready':
                        continue
                    break
                job = replace(job, phase='activating')
                job = save(job)
                outcome = await supervisor.run(lambda: host.adopt(job.candidate_id, active_evidence),
                    timeout=phase_timeout(job), signal=signal)
                if not isinstance(outcome, AdoptionResult):
                    raise TypeError('activation must return a confirmed adoption result')
                if outcome.status == 'rejected' and continue_on_rejection:
                    reason = controller.finish(steps=job.steps, limit=job.max_steps, outcome='not_adopted')
                    job = save(replace(job, phase='complete' if reason else 'ready', candidate_id='', evidence=None,
                        stop_reason=reason or '', consecutive_no_gain=controller.consecutive_no_gain,
                        consecutive_failures=controller.consecutive_failures))
                    continue
                if outcome.status != 'activated':
                    job = replace(job, phase=outcome.status)
                    job = save(job)
                    break
                if outcome.manifest_digest != host.active_manifest() or not host.is_active(job.candidate_id):
                    raise ValueError('host activation identity mismatch')
                reason = controller.finish(steps=job.steps, limit=job.max_steps, outcome='adopted', assurance='verified',
                    score=active_evidence.score, policy_id=job.policy_id, run_id='generation-' + str(job.steps))
                job = replace(job, phase='complete' if reason else 'ready', current_manifest=outcome.manifest_digest,
                              candidate_id='', evidence=None, stop_reason=reason or '',
                              consecutive_no_gain=controller.consecutive_no_gain, consecutive_failures=controller.consecutive_failures)
                job = save(job)
        return job
