"""One completed model evaluator supplies evidence-grounded feedback and comparison."""
import asyncio
from dataclasses import replace
import json
import unittest

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.data_model import AssistantMessage,TextBlock
from fruitfly_agent.core.model_stream import AssistantMessageEventStream,StreamDone
from fruitfly_agent.improvement.contracts.tasks import TaskMaterial,Resource
from fruitfly_agent.improvement.execution.facts import ensure_facts,receipt_facts,attach_facts,read_facts
from fruitfly_agent.improvement.workflow.services import WorkflowServices
from fruitfly_agent.lab.improvement.assessment.completed import CompletedAssessmentService
from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts
from fruitfly_agent.lab.improvement.strategies.exploration import ExplorationRegistry,ExplorationDefinition
from tests.support.faux_provider import FauxProvider
from tests.support.model_evaluation import judgment
from tests.support.pipeline import build_pipeline,Runner


def judge_response(view,signal=None):
    async def stream():yield StreamDone(judgment(view))
    return AssistantMessageEventStream(stream())


class CompletedImprovementTests(unittest.IsolatedAsyncioTestCase):
    async def prepare(self,*,provider=None,timeouts=None):
        _,plan,baseline,_=build_pipeline()
        if timeouts:plan=replace(plan,timeouts=timeouts)
        artifacts=MemoryArtifacts();services=WorkflowServices(plan)
        task=TaskMaterial('task','Supply the requested deliverable')
        record=ensure_facts(await Runner().execute(plan,task,baseline),artifacts)
        provider=provider or FauxProvider()
        service=CompletedAssessmentService(config=AgentLoopConfig(provider=provider,model='assessor'),artifacts=artifacts,services=services)
        self.addAsyncCleanup(services.close)
        return service,record,task,services,provider

    async def test_completed_dimensions_persist_with_source_identity(self):
        service,record,task,services,provider=await self.prepare()
        provider.script=[judge_response]
        assessed,values=await service.assess(task,record)
        self.assertEqual(values[0].status,'final')
        self.assertTrue(values[0].dimensions)
        self.assertTrue(any(r.path=='assessment.json'for r in assessed.artifacts))
        self.assertEqual(record.artifacts,assessed.artifacts[:-1])
        self.assertEqual(provider.calls[0]['model'],'assessor')
        self.assertEqual(set(provider.calls[0]['tools']),{'catalog','search','read'})

    async def test_invalid_json_and_intermediate_answers_are_unavailable(self):
        for intermediate in (False,True):
            with self.subTest(intermediate=intermediate):
                service,record,task,services,provider=await self.prepare()
                provider.respond(AssistantMessage([TextBlock('not JSON')],stop_reason='stop',continue_turn=intermediate))
                if intermediate:provider.respond_fatal('unfinished judge')
                assessed,values=await service.assess(task,record)
                self.assertEqual(values[0].status,'unavailable')
                self.assertEqual(assessed.status,record.status)

    async def test_repeated_assessments_have_no_shared_request_allowance(self):
        service,record,task,services,provider=await self.prepare()
        provider.script=[judge_response]*20
        for _ in range(20):
            _,values=await service.assess(task,record)
            self.assertEqual(values[0].status,'final')
        self.assertEqual(services.used['model'],20)
        self.assertTrue(all(set(c['tools'])=={'catalog','search','read'}for c in provider.calls))

    async def test_comparison_does_not_require_prior_individual_assessments(self):
        service,record,task,services,provider=await self.prepare()
        other=replace(record,run_id='other')
        other=replace(other,artifacts=())
        other=ensure_facts(other,service.artifacts)
        provider.script=[judge_response]
        decision=await service.compare(task,(record,other),record)
        self.assertEqual(decision.run_id,'other')
        self.assertEqual(len(provider.calls),1)
        self.assertEqual(service.values,{})

    async def test_forged_facts_cannot_expose_private_artifacts(self):
        service,record,task,services,provider=await self.prepare()
        record=replace(record,artifacts=())
        private=service.artifacts.put(b'PRIVATE CHECK ANSWER')
        facts=replace(receipt_facts(record,service.artifacts),evidence=(Resource('private',private),))
        forged=attach_facts(record,facts,service.artifacts)
        with self.assertRaisesRegex(ValueError,'outside'):read_facts(forged,service.artifacts)
        self.assertEqual(provider.calls,[])

    async def test_streams_close_on_completion_timeout_and_cancellation(self):
        for mode in ('complete','timeout','cancel'):
            with self.subTest(mode=mode):
                entered,closed=asyncio.Event(),asyncio.Event()
                def response(view,signal=None):
                    async def stream():
                        try:
                            entered.set()
                            if mode!='complete':await asyncio.Event().wait()
                            yield StreamDone(judgment(view))
                        finally:closed.set()
                    return AssistantMessageEventStream(stream())
                provider=FauxProvider();provider.script=[response]
                service,record,task,services,_=await self.prepare(provider=provider,timeouts={'editor_seconds':1,'execution_seconds':1,'evaluator_seconds':.03})
                pending=asyncio.create_task(service.assess(task,record))
                await asyncio.wait_for(entered.wait(),1)
                if mode=='cancel':
                    pending.cancel()
                    with self.assertRaises(asyncio.CancelledError):await pending
                else:
                    _,values=await pending
                    self.assertEqual(values[0].status,'final'if mode=='complete'else'unavailable')
                self.assertTrue(closed.is_set())

    async def test_invalid_exploration_factory_products_are_owned_before_validation(self):
        _,_,_,services,_=await self.prepare();closed=[]
        class Invalid:
            async def aclose(self):closed.append(self)
        product=Invalid()
        registry=ExplorationRegistry((ExplorationDefinition('custom','custom',lambda:product),))
        with self.assertRaises(ValueError):registry.create('custom',own=services.own)
        await services.close();self.assertEqual(closed,[product])
