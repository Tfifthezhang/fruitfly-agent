"""Reliability behavior and failure contracts."""
import asyncio
from dataclasses import replace
import unittest
from unittest.mock import AsyncMock
from fruitfly_agent.improvement.contracts.failures import IntegrityError, PersistenceError, CleanupError
from fruitfly_agent.improvement.execution.facts import attach_facts, receipt_facts
from fruitfly_agent.improvement.stages.services import StageServices
from fruitfly_agent.improvement.contracts.tasks import TaskMaterial
from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts
from tests.support.stages import proposal_fixture


class ReliabilityTests(unittest.IsolatedAsyncioTestCase):





    async def test_cleanup_attempts_all_resources(self):
        _, plan, _, _ = proposal_fixture()
        closed = []
        class Resource:
            def __init__(self, name): self.name = name
            async def aclose(self):
                closed.append(self.name)
                if self.name == 'bad': raise OSError('failed close')
        services = StageServices(plan)
        services.own(Resource('good')); services.own(Resource('bad'))
        with self.assertRaises(CleanupError): await services.close()
        self.assertEqual(closed, ['bad', 'good'])
        self.assertEqual(services.resources, [])
