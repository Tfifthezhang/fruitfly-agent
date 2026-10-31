"""Bounded read-only evaluation, observed citations and prompt candidate execution."""
from dataclasses import replace
import json
from types import SimpleNamespace
import unittest
from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.data_model import UserMessage, AssistantMessage, TextBlock
from fruitfly_agent.improvement.contracts.assessment import AssessmentUnavailable
from fruitfly_agent.improvement.contracts.execution import ExecutionRecord
from fruitfly_agent.improvement.contracts.tasks import TaskMaterial, Resource
from fruitfly_agent.improvement.contracts.plans import RunPlan
from fruitfly_agent.improvement.workflow.services import WorkflowServices
from fruitfly_agent.lab.improvement.assessment.evaluator import ModelEvaluator
from fruitfly_agent.lab.improvement.assessment.instructions import EvaluatorInstructions, EvaluatorInstructionTarget
from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts
from tests.support.faux_provider import FauxProvider
from tests.support.pipeline import version
from tests.support.model_evaluation import judgment


class EvaluatorTests(unittest.IsolatedAsyncioTestCase):
    def setup_evaluation(self):
        artifacts = MemoryArtifacts()
        plan = RunPlan('evaluation', version(), ('prompt',))
        task = TaskMaterial('task', 'Return the requested result and report checks.')
        log = artifacts.put(b'noise ' * 800000 + b' decisive evidence')
        records = tuple(ExecutionRecord('run-' + str(i), task.task_id, task.material_id,
            plan.parent.harness, plan.parent.state, plan.conditions_id, 'completed', 'output ' + str(i),
            (Resource('trajectory.txt', log, kind='trajectory'),)) for i in range(2))
        provider = FauxProvider()
        evaluator = ModelEvaluator(AgentLoopConfig(provider), artifacts)
        services = WorkflowServices(plan)
        self.addAsyncCleanup(services.close)
        return evaluator, task, records, services, provider, log

    async def test_initial_evidence_lists_full_index_without_reading_large_trajectory(self):
        evaluator, task, records, services, provider, log = self.setup_evaluation()
        calls = []
        original = evaluator.artifacts.read
        def read(reference): calls.append(reference); return original(reference)
        evaluator.artifacts.read = read
        # Use the regular FauxProvider response callable protocol.
        from fruitfly_agent.core.model_stream import AssistantMessageEventStream, StreamDone
        def reply(view, signal=None):
            async def events(): yield StreamDone(judgment(view))
            return AssistantMessageEventStream(events())
        provider.script = [reply]
        result, reference = await evaluator.evaluate(task, records, services)
        self.assertEqual(records[-1].run_id, result['choice'])
        self.assertNotIn(log, calls)
        self.assertEqual(1, services.used['model'])
        initial = json.loads(provider.calls[0]['messages'][0].content)
        self.assertIn('catalog', initial)
        self.assertLessEqual(set(provider.calls[0]['tools']), {'catalog', 'read', 'search'})
        self.assertTrue(result['evaluations'][0]['dimensions'])

    async def test_search_supplies_only_returned_spans_and_keeps_tools_available(self):
        evaluator, task, records, services, provider, log = self.setup_evaluation()
        provider.respond_tool_call('search', {'path': 'context/executions/run-0/trajectory.txt', 'query': 'decisive'})
        from fruitfly_agent.core.model_stream import AssistantMessageEventStream, StreamDone
        def finish(view, signal=None):
            self.assertEqual({'catalog', 'read', 'search'}, {tool.name for tool in view.tools})
            data = json.loads(judgment(view).text)
            data['evidence_ids'] = [json.loads(view.messages[-1].text)['matches'][0]['citation_id']]
            async def events(): yield StreamDone(AssistantMessage([TextBlock(json.dumps(data))], stop_reason='stop'))
            return AssistantMessageEventStream(events())
        provider.script.append(finish)
        result, _ = await evaluator.evaluate(task, records, services)
        self.assertNotEqual([log], result['evidence_ids'])
        self.assertEqual(2, services.used['model'])
        for empty_read in (False, True):
            with self.subTest(empty_read=empty_read):
                evaluator, task, records, services, provider, log = self.setup_evaluation()
                def forged(view, signal=None):
                    data = json.loads(judgment(view).text); data['evidence_ids'] = [log]
                    async def events(): yield StreamDone(AssistantMessage([TextBlock(json.dumps(data))], stop_reason='stop'))
                    return AssistantMessageEventStream(events())
                if empty_read:
                    provider.respond_tool_call('read', {'path': 'context/executions/run-0/trajectory.txt', 'offset': 9000000})
                provider.script.append(forged)
                with self.assertRaises(AssessmentUnavailable): await evaluator.evaluate(task, records, services)

    async def test_evaluator_candidate_changes_actual_judgment_prompt_and_keeps_host_rules(self):
        evaluator, task, records, services, provider, _ = self.setup_evaluation()
        target = EvaluatorInstructionTarget()
        text = json.loads(target.snapshot().text)
        text['instructions']['compare'] = 'CANDIDATE: compare verification evidence first.'
        source = json.dumps(text)
        target.validate_change(source, {'editable_fields': ['parameters.instructions.compare']})
        changed = EvaluatorInstructionTarget.parse(source)
        from fruitfly_agent.core.model_stream import AssistantMessageEventStream, StreamDone
        def reply(view, signal=None):
            choice = -1 if 'CANDIDATE' in view.system_prompt else 0
            async def events(): yield StreamDone(judgment(view, choice=choice))
            return AssistantMessageEventStream(events())
        choices = []
        for instructions in (target.instructions, changed):
            provider.script = [reply]
            instance = ModelEvaluator(AgentLoopConfig(provider), evaluator.artifacts, instructions=instructions)
            data, _ = await instance.evaluate(task, records, services)
            choices.append(data['choice'])
        self.assertEqual(['run-0', 'run-1'], choices)
        self.assertEqual(target.instructions, EvaluatorInstructions())
        self.assertTrue(all('no editing' in c['system_prompt'] for c in provider.calls))
