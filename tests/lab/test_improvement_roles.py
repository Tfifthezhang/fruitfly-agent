"""Every role uses the same lifecycle while identity and policies stay fixed."""
import asyncio
from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

from fruitfly_agent.lab.improvement.contracts.versions import SystemVersion, content_hash
from fruitfly_agent.lab.improvement.contracts.candidates import TargetRegistry, TargetChange, VersionCandidate
from fruitfly_agent.lab.improvement.contracts import ImprovementRequest, ComparisonEvidence
from fruitfly_agent.lab.improvement.runtime.workflow import ImprovementWorkflow, ImprovementCapability
from fruitfly_agent.lab.improvement.methods.opro import OproImprover
from fruitfly_agent.lab.algorithms.targets import TargetSnapshot, TargetBinding


class ImprovementRoleTests(unittest.IsolatedAsyncioTestCase):
    def setup_role(self, role):
        parent = SystemVersion(*(content_hash(v) for v in ('H', 'I', 'S')))
        field = {'H': 'harness', 'S': 'state', 'I': 'improver'}[role]
        version = replace(parent, **{field: content_hash('new')})
        candidate = VersionCandidate(parent, version, (TargetChange(role, 'target', 'test-v1', content_hash('old'), content_hash('new')),))
        request = ImprovementRequest(role, 'target', parent, content_hash('fixed conditions'), 'fixed-policy', 'Improve tasks')
        evidence = ComparisonEvidence(candidate.candidate_id, request.conditions_id, request.policy_id, True)
        targets = TargetRegistry()
        targets.register(role, 'target', 'test-v1', SimpleNamespace(validate_change=Mock()))
        workflow = ImprovementWorkflow(targets)
        adapter = SimpleNamespace(prepare=AsyncMock(return_value=object()), close=AsyncMock())
        comparison = SimpleNamespace(compare=AsyncMock(return_value=evidence))
        workflow.register(role, 'target', request.policy_id, ImprovementCapability(adapter, comparison))
        return workflow, request, candidate, evidence, adapter, comparison

    async def test_each_role_verifies_and_adopts_the_exact_version(self):
        for role in ('H', 'S', 'I'):
            with self.subTest(role=role):
                flow, request, candidate, evidence, adapter, compare = self.setup_role(role)
                active = [request.parent]
                async def adopt(req, proposed, proof):
                    self.assertEqual((req, proposed, proof), (request, candidate, evidence))
                    active[0] = proposed.version
                result = await flow.run(request, generate=AsyncMock(return_value=candidate),
                    active_version=lambda: active[0], adopt=adopt)
                self.assertEqual(result, (candidate, evidence))
                self.assertEqual(active[0], candidate.version)
                adapter.close.assert_awaited_once()

    async def test_rejected_candidate_never_activates(self):
        flow, request, candidate, evidence, adapter, compare = self.setup_role('S')
        compare.compare.return_value = replace(evidence, passed=False)
        adopt = AsyncMock()
        await flow.run(request, generate=AsyncMock(return_value=candidate), active_version=lambda: request.parent, adopt=adopt)
        adopt.assert_not_awaited()
        adapter.close.assert_awaited_once()

    async def test_unknown_scope_stale_parent_and_changed_conditions_reject(self):
        for mode in ('unknown', 'stale', 'conditions', 'scope'):
            with self.subTest(mode=mode):
                flow, request, candidate, evidence, adapter, compare = self.setup_role('I')
                active = request.parent
                if mode == 'unknown':
                    flow.capabilities.clear()
                elif mode == 'stale':
                    active = candidate.version
                elif mode == 'conditions':
                    compare.compare.return_value = replace(evidence, conditions_id=content_hash('different'))
                else:
                    request = replace(request, target_id='another')
                adopt = AsyncMock()
                with self.assertRaises(ValueError):
                    await flow.run(request, generate=AsyncMock(return_value=candidate), active_version=lambda: active, adopt=adopt)
                adopt.assert_not_awaited()

    async def test_cancellation_closes_trial_and_never_activates(self):
        flow, request, candidate, evidence, adapter, compare = self.setup_role('S')
        compare.compare.side_effect = asyncio.CancelledError
        adopt = AsyncMock()
        with self.assertRaises(asyncio.CancelledError):
            await flow.run(request, generate=AsyncMock(return_value=candidate), active_version=lambda: request.parent, adopt=adopt)
        adapter.close.assert_awaited_once()
        adopt.assert_not_awaited()

    async def test_current_opro_does_not_claim_state_or_improver_support(self):
        for role in ('S', 'I'):
            problem = SimpleNamespace(baseline=TargetSnapshot('target', 'text', TargetBinding('prompt'), role=role))
            with self.assertRaisesRegex(ValueError, 'H targets only'):
                await OproImprover().search(problem, None)
