"""Offline orchestration and immediate interaction; no code loading or network."""

from __future__ import annotations

import asyncio
import unittest

from fruitfly_agent.interactive import InteractiveSession
from fruitfly_agent.lab.rsi import (
    AgentVersion, Candidate, EvolutionBudget, EvolutionDriver, Verification,
)
from tests.support.faux_provider import FauxProvider
from tests.support.loop import make_config


class RsiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.initial = AgentVersion("task:0", "improver:0")
        self.candidate = Candidate(self.initial, AgentVersion("task:1", "improver:1"))
        self.generated: list[AgentVersion] = []
        self.adoptions: list[Candidate] = []

    async def generate(self, parent, feedback, *, signal):
        self.generated.append(parent)
        return self.candidate

    async def verify(self, candidate, *, signal):
        return Verification(candidate.version, "offline-policy", True, "validated")

    async def adopt(self, candidate, verification, *, signal):
        self.adoptions.append(candidate)
        return True

    def driver(self, *, generate=None, verify=None, adopt=None, budget=None):
        return EvolutionDriver(
            generator_for=lambda version: generate or self.generate,
            verify=verify or self.verify, adopt=adopt or self.adopt,
            policy_id="offline-policy", budget=budget or EvolutionBudget(max_steps=1),
        )

    async def test_adopted_improver_generates_next_version_used_in_interaction(self):
        generation_two = AgentVersion("task:2", "improver:1")
        observed = []
        provider = FauxProvider()
        provider.respond_text("done")
        runtime = None

        async def improved_generator(parent, feedback, *, signal):
            observed.append((parent, feedback))
            return Candidate(parent, generation_two)

        def resolve(version):
            return improved_generator if version.improver_artifact == "improver:1" else self.generate

        async def activate(candidate, verification, *, signal):
            nonlocal runtime
            runtime = InteractiveSession(make_config(
                provider, system_prompt=f"Bound task implementation: {candidate.version.task_artifact}",
            ))
            return True

        driver = EvolutionDriver(
            generator_for=resolve, verify=self.verify, adopt=activate,
            policy_id="offline-policy", budget=EvolutionBudget(max_steps=2),
        )
        result = await driver.evolve(self.initial, feedback="initial failure")
        self.assertEqual(generation_two, result.version)
        self.assertEqual(["adopted", "adopted"], [item.outcome for item in result.attempts])
        self.assertEqual([(self.candidate.version, "validated")], observed)
        reply = await runtime.submit("continue interactively")
        self.assertFalse(reply.is_error)
        self.assertIn("task:2", provider.calls[0]["system_prompt"])

    async def test_failed_verification_never_adopts(self):
        async def reject(candidate, *, signal):
            return Verification(candidate.version, "offline-policy", False, "failed")
        result = await self.driver(verify=reject).evolve(self.initial)
        self.assertEqual(self.initial, result.version)
        self.assertEqual("rejected", result.attempts[0].outcome)
        self.assertEqual([], self.adoptions)

    async def test_failure_feedback_is_bounded_on_the_next_proposal(self):
        observed = []
        async def fail(parent, feedback, *, signal):
            observed.append(feedback)
            raise OSError("provider or store unavailable")
        result = await self.driver(
            generate=fail, budget=EvolutionBudget(max_steps=2, max_feedback_chars=4),
        ).evolve(self.initial, feedback="initial")
        self.assertEqual(["init", "prop"], observed)
        self.assertEqual(2, len(result.attempts))
        self.assertEqual([], self.adoptions)

    async def test_stale_candidate_cannot_reach_verifier(self):
        stale = Candidate(AgentVersion("other", "other"), self.candidate.version)
        async def generate(parent, feedback, *, signal):
            return stale
        result = await self.driver(generate=generate).evolve(self.initial)
        self.assertEqual("invalid_candidate", result.attempts[0].outcome)
        self.assertEqual(self.initial, result.version)
        self.assertEqual([], self.adoptions)

    async def test_verification_must_bind_candidate_and_policy(self):
        for version, policy in ((self.initial, "offline-policy"), (self.candidate.version, "other-policy")):
            async def wrong(candidate, *, signal):
                return Verification(version, policy, True)
            result = await self.driver(verify=wrong).evolve(self.initial)
            self.assertEqual("verification_failed", result.attempts[0].outcome)
        self.assertEqual([], self.adoptions)

    async def test_failed_adoption_keeps_parent_for_next_proposal(self):
        async def decline(candidate, verification, *, signal):
            return False
        result = await self.driver(
            adopt=decline, budget=EvolutionBudget(max_steps=2),
        ).evolve(self.initial)
        self.assertEqual(self.initial, result.version)
        self.assertEqual([self.initial, self.initial], self.generated)
        self.assertEqual(["not_adopted", "not_adopted"], [a.outcome for a in result.attempts])

    async def test_adoption_exception_is_not_reported_as_successful_rollback(self):
        async def fail(candidate, verification, *, signal):
            raise RuntimeError("host must reconcile")
        with self.assertRaisesRegex(RuntimeError, "reconcile"):
            await self.driver(adopt=fail).evolve(self.initial)

    async def test_adoption_timeout_propagates_for_host_reconciliation(self):
        cleaned = asyncio.Event()
        async def stall(candidate, verification, *, signal):
            try:
                await asyncio.Event().wait()
            finally:
                cleaned.set()
        with self.assertRaises(TimeoutError):
            await self.driver(
                adopt=stall, budget=EvolutionBudget(phase_timeout_seconds=0.01),
            ).evolve(self.initial)
        self.assertTrue(cleaned.is_set())

    async def test_no_candidate_stops_without_consuming_all_steps(self):
        async def done(parent, feedback, *, signal):
            return None
        result = await self.driver(generate=done).evolve(self.initial)
        self.assertEqual("no_candidate", result.attempts[0].outcome)
        self.assertEqual(self.initial, result.version)

    async def test_timeouts_are_bounded_and_clean_up_proposal(self):
        cleaned = asyncio.Event()
        async def stall(parent, feedback, *, signal):
            try:
                await asyncio.Event().wait()
            finally:
                cleaned.set()
        result = await self.driver(
            generate=stall, budget=EvolutionBudget(max_steps=2, phase_timeout_seconds=0.01),
        ).evolve(self.initial)
        self.assertTrue(cleaned.is_set())
        self.assertEqual(2, len(result.attempts))
        self.assertTrue(all(a.outcome == "proposal_failed" for a in result.attempts))
        self.assertEqual(self.initial, result.version)

    async def test_feedback_is_bounded_and_cancel_before_adoption_propagates(self):
        signal = asyncio.Event()
        seen = []
        async def generate(parent, feedback, *, signal):
            seen.append(feedback)
            return self.candidate
        async def verify(candidate, *, signal):
            signal.set()
            return Verification(candidate.version, "offline-policy", True)
        with self.assertRaises(asyncio.CancelledError):
            await self.driver(
                generate=generate, verify=verify, budget=EvolutionBudget(max_feedback_chars=4),
            ).evolve(self.initial, feedback="long feedback", signal=signal)
        self.assertEqual(["long"], seen)
        self.assertEqual([], self.adoptions)

    async def test_hard_cancel_cleans_up_and_does_not_adopt(self):
        started = asyncio.Event()
        cleaned = asyncio.Event()
        async def stall(parent, feedback, *, signal):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleaned.set()
        task = asyncio.create_task(self.driver(generate=stall).evolve(self.initial))
        await asyncio.wait_for(started.wait(), 1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(cleaned.is_set())
        self.assertEqual([], self.adoptions)

    def test_values_and_budget_are_validated(self):
        for kwargs in ({"max_steps": True}, {"max_steps": 0}, {"max_feedback_chars": 0},
                       {"phase_timeout_seconds": float("inf")}, {"phase_timeout_seconds": 0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                EvolutionBudget(**kwargs)
        with self.assertRaises(ValueError):
            Candidate(self.initial, self.initial)
        with self.assertRaises(ValueError):
            AgentVersion("", "improver")
