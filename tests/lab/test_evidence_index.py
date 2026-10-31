"""Derived navigation and source spans preserve large immutable evidence."""
from dataclasses import replace
import json
import unittest
from fruitfly_agent.improvement.contracts.tasks import TaskMaterial,Resource
from fruitfly_agent.improvement.execution.facts import ensure_facts
from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts,EvidenceWorkspace
from fruitfly_agent.lab.improvement.evidence.indexing import organize_evidence,OVERVIEW_PATH,EVENTS_PATH
from fruitfly_agent.lab.improvement.evidence.catalog import WorkspaceEvidence
from tests.support.pipeline import build_pipeline,Runner


class EvidenceIndexTests(unittest.IsolatedAsyncioTestCase):
    async def test_navigation_is_rebuildable_and_originals_are_unchanged(self):
        _,plan,baseline,_=build_pipeline();artifacts=MemoryArtifacts();task=TaskMaterial('task','Finish')
        data='\n'.join(json.dumps({'event':'tool','data':{'elapsed_seconds':v},'message':{'role':'toolResult','is_error':False}})for v in (1,318))
        original=artifacts.put(data.encode())
        record=await Runner().execute(plan,task,baseline)
        record=replace(record,artifacts=(Resource('session.jsonl',original,'application/json','trajectory'),))
        record=ensure_facts(record,artifacts)
        indexed=organize_evidence(task,record,artifacts)
        self.assertEqual(indexed,organize_evidence(task,indexed,artifacts))
        self.assertEqual(indexed,organize_evidence(task,record,artifacts))
        self.assertEqual(artifacts.read(original),data.encode())
        rows=json.loads(artifacts.read(next(r.artifact_id for r in indexed.artifacts if r.path==EVENTS_PATH)))
        self.assertEqual(len(rows['events']),2)
        for row in rows['events']:self.assertTrue(json.loads(data[row['start']:row['end']]))
        self.assertTrue(any(r.path==OVERVIEW_PATH for r in indexed.artifacts))

    async def test_cross_file_search_pages_cover_hidden_failure_without_whole_file_citation(self):
        _,_,baseline,_=build_pipeline()
        text='ok\n'*10000+'compiler error hidden by echo\n'
        workspace=EvidenceWorkspace(baseline=baseline,files={'first.txt':text.encode(),'second.txt':b'compiler error again'},writable_ids=())
        reader=WorkspaceEvidence(workspace)
        page=reader.search('compiler error',limit=1)
        self.assertEqual(len(page['matches']),1);self.assertIsNotNone(page['next_cursor'])
        match=page['matches'][0]
        self.assertIn('hidden by echo',match['text'])
        self.assertIn(match['citation_id'],workspace.provided_ids)
        self.assertNotIn(match['artifact_id'],workspace.provided_ids)
        tail=reader.search('compiler error',limit=1,cursor=page['next_cursor'])
        self.assertEqual(tail['matches'][0]['path'],'second.txt')
        with self.assertRaises(ValueError):reader.search('different',cursor=page['next_cursor'])

    async def test_catalog_pages_are_navigation_not_evidence_supply(self):
        _,_,baseline,_=build_pipeline()
        workspace=EvidenceWorkspace(baseline=baseline,files={'a':b'0123456789','b':b'other'},writable_ids=())
        reader=WorkspaceEvidence(workspace)
        result=reader.catalog(limit=1)
        self.assertIsNotNone(result['next_cursor']);self.assertEqual(workspace.provided_ids,set())
        page=reader.read('a',offset=3,limit=2)
        self.assertEqual((page['start'],page['end'],page['text'],page['next_offset']),(3,5,'34',5))
        with self.assertRaises(ValueError):reader.search('x',paths=('outside',))

    async def test_event_directory_decodes_native_payload_without_modifying_original(self):
        _, plan, baseline, _ = build_pipeline()
        artifacts = MemoryArtifacts()
        task = TaskMaterial('task', 'Inspect failures')
        raw = json.dumps({'kind': 'tool-finished', 'position': {'sequence': 1},
                          'payload_json': json.dumps({'tool_name': 'bash', 'is_error': True,
                                                       'elapsed_seconds': 318})})
        record = await Runner().execute(plan, task, baseline)
        record = replace(record, artifacts=(Resource('events.jsonl', artifacts.put(raw.encode()),
                                                       'application/json', 'trajectory'),))
        indexed = organize_evidence(task, ensure_facts(record, artifacts), artifacts)
        index = json.loads(artifacts.read(next(r.artifact_id for r in indexed.artifacts if r.path == EVENTS_PATH)))
        event = index['events'][0]
        self.assertEqual((event['kind'], event['tool_name'], event['is_error'], event['elapsed_seconds']),
                         ('tool-finished', 'bash', True, 318))
        self.assertEqual(raw[event['start']:event['end']], raw)
