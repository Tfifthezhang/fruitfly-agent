"""Bounded RSI policy orchestration; code loading and adoption belong to hosts."""

from __future__ import annotations

import asyncio
from typing import Callable, Protocol

from .models import (
    AgentVersion, Candidate, EvolutionAttempt, EvolutionBudget, EvolutionResult, Verification,
)


class CandidateGenerator(Protocol):
    async def __call__(
        self, parent: AgentVersion, feedback: str, *, signal: asyncio.Event | None,
    ) -> Candidate | None: ...


class CandidateVerifier(Protocol):
    async def __call__(
        self, candidate: Candidate, *, signal: asyncio.Event | None,
    ) -> Verification: ...


class CandidateAdopter(Protocol):
    async def __call__(
        self, candidate: Candidate, verification: Verification, *, signal: asyncio.Event | None,
    ) -> bool:
        """True only after activation; False must leave the prior version active.

        The host owns atomic activation, cancellation cleanup and active-version
        reconciliation after exceptions. A successful return must also bind the
        next generation's task/improver. Never mutate a live implementation here.
        """
        ...


class EvolutionDriver:
    """Resolve the current improver anew after every successfully adopted version.

    Generator/verifier failures retain a research record and do not invoke
    adoption. Adoption errors propagate: orchestration cannot infer or roll
    back a host's external side effects. No implicit Provider calls, filesystem
    access, CLI registration, artifact persistence or sandboxing are performed.
    """

    def __init__(
        self,
        *,
        generator_for: Callable[[AgentVersion], CandidateGenerator],
        verify: CandidateVerifier,
        adopt: CandidateAdopter,
        policy_id: str,
        budget: EvolutionBudget | None = None,
    ) -> None:
        if not isinstance(policy_id, str) or not policy_id.strip():
            raise ValueError("policy_id must be non-empty")
        if budget is not None and not isinstance(budget, EvolutionBudget):
            raise TypeError("budget must be an EvolutionBudget")
        self.generator_for = generator_for
        self.verify = verify
        self.adopt = adopt
        self.policy_id = policy_id
        self.budget = budget or EvolutionBudget()

    async def evolve(
        self,
        initial: AgentVersion,
        *,
        feedback: str = "",
        signal: asyncio.Event | None = None,
    ) -> EvolutionResult:
        if not isinstance(initial, AgentVersion) or not isinstance(feedback, str):
            raise TypeError("evolve requires an AgentVersion and text feedback")
        current = initial
        attempts: list[EvolutionAttempt] = []
        feedback = feedback[:self.budget.max_feedback_chars]
        for _ in range(self.budget.max_steps):
            self._check_cancelled(signal)
            feedback = feedback[:self.budget.max_feedback_chars]
            try:
                generator = self.generator_for(current)
                async with asyncio.timeout(self.budget.phase_timeout_seconds):
                    candidate = await generator(current, feedback, signal=signal)
            except Exception as exc:
                feedback = f"proposal failed: {type(exc).__name__}"
                attempts.append(EvolutionAttempt(current, None, None, "proposal_failed", feedback))
                continue
            self._check_cancelled(signal)
            if candidate is None:
                attempts.append(EvolutionAttempt(current, None, None, "no_candidate"))
                break
            if not isinstance(candidate, Candidate) or candidate.parent != current:
                feedback = "candidate type or parent version mismatch"
                attempts.append(EvolutionAttempt(current, None, None, "invalid_candidate", feedback))
                continue
            try:
                async with asyncio.timeout(self.budget.phase_timeout_seconds):
                    verification = await self.verify(candidate, signal=signal)
                if (
                    not isinstance(verification, Verification)
                    or verification.version != candidate.version
                    or verification.policy_id != self.policy_id
                ):
                    raise ValueError("verification candidate or policy mismatch")
            except Exception as exc:
                feedback = f"verification failed: {type(exc).__name__}"
                attempts.append(EvolutionAttempt(current, candidate, None, "verification_failed", feedback))
                continue
            self._check_cancelled(signal)
            feedback = verification.feedback[:self.budget.max_feedback_chars]
            if not verification.passed:
                attempts.append(EvolutionAttempt(current, candidate, verification, "rejected", feedback))
                continue
            # Errors here must surface to the host rather than claiming rollback.
            async with asyncio.timeout(self.budget.phase_timeout_seconds):
                adopted = await self.adopt(candidate, verification, signal=signal)
            if not isinstance(adopted, bool):
                raise TypeError("adopter must return bool and reconcile its active version")
            attempts.append(EvolutionAttempt(
                current, candidate, verification,
                "adopted" if adopted else "not_adopted", feedback,
            ))
            if adopted:
                current = candidate.version
        return EvolutionResult(current, tuple(attempts))

    @staticmethod
    def _check_cancelled(signal: asyncio.Event | None) -> None:
        if signal is not None and signal.is_set():
            raise asyncio.CancelledError


__all__ = ["CandidateGenerator", "CandidateVerifier", "CandidateAdopter", "EvolutionDriver"]
