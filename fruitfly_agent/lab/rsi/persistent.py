"""Bounded resumable text evolution using the same host inbox as human optimization."""
from dataclasses import replace
import asyncio
from fruitfly_agent.lab.algorithms import Algorithm, AlgorithmSpec
from fruitfly_agent.lab.algorithms.evolution import EvolutionHost, EvolutionJob


class PersistentEvolutionDriver(Algorithm):
    spec = AlgorithmSpec('persistent-text-evolution', 'persistent-text-v1', 'workspace')

    async def evolve(self, host: EvolutionHost, *, job_id: str, policy_id: str,
                     direction: str, max_steps: int = 2, phase_timeout_seconds: float = 60.0, signal=None) -> EvolutionJob:
        if not job_id or not policy_id or not direction.strip() or isinstance(max_steps, bool) or max_steps < 1:
            raise ValueError('job, policy, direction and a positive step budget are required')
        job = host.load_job(job_id)
        if job is None:
            job = EvolutionJob(job_id, policy_id, direction, host.active_manifest(), max_steps, phase_timeout_seconds)
            host.save_job(job)
        elif (job.policy_id, job.direction, job.max_steps, job.phase_timeout_seconds) != (policy_id, direction, max_steps, phase_timeout_seconds):
            raise ValueError('persisted evolution job parameters differ')
        if job.phase == 'activating':
            # Reconcile an interrupted commit; never blindly replay adoption.
            if host.is_active(job.candidate_id):
                job = replace(job, phase='ready', current_manifest=host.active_manifest(), candidate_id='', evidence=None)
            else:
                job = replace(job, phase='interrupted')
            host.save_job(job)
        elif job.phase in {'proposing', 'verifying'}:
            # Model/verification cost may already have been consumed before crash.
            job = replace(job, phase='interrupted')
            host.save_job(job)
        if job.current_manifest != host.active_manifest():
            raise ValueError('evolution job active version is stale')
        while job.phase in {'ready', 'proposed', 'verified'} and job.steps <= job.max_steps:
            if signal is not None and signal.is_set():
                raise asyncio.CancelledError
            if job.phase == 'ready':
                if job.steps == job.max_steps:
                    job = replace(job, phase='complete')
                    host.save_job(job)
                    break
                job = replace(job, phase='proposing', steps=job.steps + 1)
                host.save_job(job)
                async with asyncio.timeout(job.phase_timeout_seconds):
                    candidate_id = await host.propose(job.direction)
                if candidate_id is None:
                    job = replace(job, phase='complete')
                    host.save_job(job)
                    break
                job = replace(job, phase='proposed', candidate_id=candidate_id)
                host.save_job(job)
            if job.phase == 'proposed':
                job = replace(job, phase='verifying')
                host.save_job(job)
                async with asyncio.timeout(job.phase_timeout_seconds):
                    evidence = await host.verify(job.candidate_id, job.policy_id)
                if evidence.candidate_id != job.candidate_id or evidence.policy_id != job.policy_id or evidence.parent_manifest_digest != job.current_manifest:
                    raise ValueError('verification candidate, policy or parent mismatch')
                job = replace(job, phase='verified', evidence=evidence)
                host.save_job(job)
            if job.phase == 'verified':
                if signal is not None and signal.is_set():
                    raise asyncio.CancelledError
                if not job.evidence.passed:
                    job = replace(job, phase='rejected')
                    host.save_job(job)
                    break
                job = replace(job, phase='activating')
                host.save_job(job)
                async with asyncio.timeout(job.phase_timeout_seconds):
                    outcome = await host.adopt(job.candidate_id, job.evidence)
                if outcome.status != 'activated':
                    job = replace(job, phase=outcome.status)
                    host.save_job(job)
                    break
                if outcome.manifest_digest != host.active_manifest() or not host.is_active(job.candidate_id):
                    raise ValueError('host activation identity mismatch')
                job = replace(job, phase='ready', current_manifest=outcome.manifest_digest,
                              candidate_id='', evidence=None)
                host.save_job(job)
        return job
