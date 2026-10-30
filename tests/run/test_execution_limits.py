"""Configured limits reach live assembly and detached trials, with frozen identity."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.session import Session
from fruitfly_agent.lab.catalog import builtin_catalog
from fruitfly_agent.lab.improvement.execution.file_runner import FileTaskRunner
from fruitfly_agent.improvement.contracts.tasks import TaskMaterial
from fruitfly_agent.improvement.workflow.services import WorkflowServices
from fruitfly_agent.improvement.execution.facts import read_facts
from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts
from fruitfly_agent.run import HarnessConfig, HarnessProfile, build_runtime, load_harness_config, save_harness_config
from fruitfly_agent.run.runtime.manifest import execution_version_payload
from tests.support.faux_provider import FauxProvider
from tests.support.pipeline import fixture, version
from tests.support.run import _write_catalog
from fruitfly_agent.improvement.contracts.plans import RunPlan


class ExecutionLimitTests(unittest.IsolatedAsyncioTestCase):
    def test_profile_roundtrip_and_manifest_distinguish_the_actual_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_catalog(root / 'models.yaml', {'offline': 'offline-model'})
            providers = Mock()
            providers.create.side_effect = lambda *args: FauxProvider()
            profile = HarnessProfile('baseline', model_profile='offline', execution={'max_tool_calls_per_turn': 128})
            path = root / 'config.yaml'
            save_harness_config(path, HarnessConfig('baseline', {'baseline': profile}))
            self.assertEqual(load_harness_config(path).select().to_runtime_dict(), profile.to_runtime_dict())
            with Session(root / 'one.jsonl') as session:
                changed = build_runtime(profile, config_path=path, catalog=builtin_catalog(), environment={},
                    session=session, cwd=root, provider_registry=providers)
            with Session(root / 'two.jsonl') as session:
                default = build_runtime(replace(profile, execution={}), config_path=path, catalog=builtin_catalog(),
                    environment={}, session=session, cwd=root, provider_registry=providers)
            self.assertEqual(changed.config.max_tool_calls_per_turn, 128)
            self.assertEqual(default.config.max_tool_calls_per_turn, 64)
            self.assertEqual(changed.manifest.to_dict()['execution'], {
                'max_tool_calls_per_turn': 128, 'max_turns': 32, 'max_context_recovery_attempts': 6,
                'tool_execution': {'max_parallel': 8, 'default_execution_mode': 'parallel'}})
            self.assertNotEqual(execution_version_payload(changed.manifest.to_dict(), 'source'),
                execution_version_payload(default.manifest.to_dict(), 'source'))
        for execution in ({'max_tool_calls_per_turn': True}, {'max_tool_calls_per_turn': -1}, {'unknown': 2}):
            with self.subTest(execution=execution), self.assertRaises(ValueError):
                HarnessProfile('baseline', execution=execution)

    async def test_file_trial_preserves_configured_limit_and_records_what_was_delivered(self):
        registry, baseline = fixture()
        artifacts = MemoryArtifacts()
        provider = FauxProvider()
        provider.respond_tool_call('write', {'path': 'answer.txt', 'content': 'first'})
        provider.respond_tool_call('write', {'path': 'other.txt', 'content': 'skipped'})
        plan = RunPlan('limits', version(), ('prompt',))
        services = WorkflowServices(plan)
        runner = FileTaskRunner(AgentLoopConfig(provider=provider, max_tool_calls_per_turn=1), registry, artifacts, services)
        try:
            result = await runner.execute(plan, TaskMaterial('task', 'Create an answer.'), baseline)
            facts = read_facts(result, artifacts)
            self.assertEqual(facts.termination_reason, 'tool_budget_exhausted')
            self.assertEqual(facts.budgets[0].limit, 1)
            self.assertEqual(dict(facts.counters)['tool_started'], 1)
            self.assertEqual([a.path for a in facts.artifacts], ['deliverables/answer.txt'])
            self.assertEqual(result.status, 'completed')
        finally:
            await services.close()
