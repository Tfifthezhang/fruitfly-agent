"""In-memory callback host for the same generation state machine as durable hosts."""
import asyncio
from typing import Protocol

from .models import AgentVersion, Candidate, Verification, EvolutionAttempt, EvolutionBudget, EvolutionResult
from .contracts import VerificationEvidence, AdoptionResult
from .engine import EvolutionEngine
from fruitfly_agent.core.extensions.operations import OperationSupervisor


class CandidateGenerator(Protocol):
    async def __call__(self, parent: AgentVersion, feedback: str, *, signal: asyncio.Event | None) -> Candidate | None: ...


class CandidateVerifier(Protocol):
    async def __call__(self, candidate: Candidate, *, signal: asyncio.Event | None) -> Verification: ...


class CandidateAdopter(Protocol):
    async def __call__(self, candidate: Candidate, verification: Verification, *, signal: asyncio.Event | None) -> bool: ...


class InvalidCandidate(ValueError):
    pass


class CallbackHost:
    def __init__(self, driver, initial, feedback, signal):
        self.driver, self.current, self.feedback, self.signal = driver, initial, feedback, signal
        self.job = None
        self.attempts = []
        self.candidate = self.verification = None
        self.active_candidate = ''

    def active_manifest(self):
        from fruitfly_agent.improvement.contracts.versions import content_hash, canonical_json
        return content_hash(canonical_json([self.current.task_artifact, self.current.improver_artifact]))

    def load_job(self, job_id):
        return self.job

    def save_job(self, job):
        self.job = job

    def is_active(self, candidate_id):
        return candidate_id == self.active_candidate

    async def propose(self, direction):
        self.candidate = self.verification = None
        self.feedback = self.feedback[:self.driver.budget.max_feedback_chars]
        generator = self.driver.generator_for(self.current)
        candidate = await OperationSupervisor().run(lambda:generator(self.current,self.feedback,signal=self.signal),timeout=self.driver.budget.timeouts.editor_seconds,signal=self.signal)
        if candidate is None:
            self.attempts.append(EvolutionAttempt(self.current, None, None, 'no_candidate'))
            return None
        if not isinstance(candidate, Candidate) or candidate.parent != self.current:
            raise InvalidCandidate('candidate type or parent version mismatch')
        self.candidate = candidate
        return 'candidate-' + str(self.job.steps)

    async def verify(self, candidate_id, policy_id):
        value = await OperationSupervisor().run(lambda:self.driver.verify(self.candidate,signal=self.signal),timeout=self.driver.budget.timeouts.evaluator_seconds,signal=self.signal)
        if not isinstance(value, Verification) or value.version != self.candidate.version or value.policy_id != policy_id:
            raise ValueError('verification candidate or policy mismatch')
        self.verification = value
        self.feedback = value.feedback[:self.driver.budget.max_feedback_chars]
        if not value.passed:
            self.attempts.append(EvolutionAttempt(self.current, self.candidate, value, 'rejected', self.feedback))
        return VerificationEvidence(candidate_id, candidate_id, self.active_manifest(), policy_id,
            value.passed, value.feedback, value.score)

    async def adopt(self, candidate_id, evidence):
        adopted = await OperationSupervisor().run(lambda:self.driver.adopt(self.candidate,self.verification,signal=self.signal),timeout=self.driver.budget.timeouts.execution_seconds,signal=self.signal)
        if not isinstance(adopted, bool):
            raise TypeError('adopter must return bool and reconcile its active version')
        self.attempts.append(EvolutionAttempt(self.current, self.candidate, self.verification,
            'adopted' if adopted else 'not_adopted', self.feedback))
        if adopted:
            self.current = self.candidate.version
            self.active_candidate = candidate_id
        return AdoptionResult('activated' if adopted else 'rejected', self.active_manifest() if adopted else '')

    def recover(self, phase, error):
        invalid = isinstance(error, InvalidCandidate)
        outcome = 'invalid_candidate' if invalid else phase + '_failed'
        self.feedback = str(error) if invalid else phase + ' failed: ' + type(error).__name__
        self.attempts.append(EvolutionAttempt(self.current, self.candidate, None, outcome, self.feedback))
        return True


class EvolutionDriver:
    """Callback convenience API; all loop transitions belong to EvolutionEngine."""
    def __init__(self, *, generator_for, verify, adopt, policy_id, budget=None, stop_policy=None):
        if not isinstance(policy_id, str) or not policy_id.strip():
            raise ValueError('policy_id must be non-empty')
        if budget is not None and not isinstance(budget, EvolutionBudget):
            raise TypeError('budget must be an EvolutionBudget')
        if stop_policy is not None and not callable(getattr(stop_policy, 'decide', None)):
            raise ValueError('stop policy must implement decide')
        self.generator_for, self.verify, self.adopt = generator_for, verify, adopt
        self.policy_id, self.budget, self.stop_policy = policy_id, budget or EvolutionBudget(), stop_policy

    async def evolve(self, initial, *, feedback='', signal=None):
        if not isinstance(initial, AgentVersion) or not isinstance(feedback, str):
            raise TypeError('evolve requires an AgentVersion and text feedback')
        host = CallbackHost(self, initial, feedback, signal)
        job = await EvolutionEngine().evolve(host, job_id='callback', policy_id=self.policy_id,
            direction='Improve current version', max_steps=self.budget.max_steps,
            signal=signal,
            continue_on_rejection=True, stop_policy=self.stop_policy, failure_handler=host.recover)
        return EvolutionResult(host.current, tuple(host.attempts), job.stop_reason)
