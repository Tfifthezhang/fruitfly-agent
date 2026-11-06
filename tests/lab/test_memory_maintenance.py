"""Thresholds count source increments without auxiliary recall requests."""
from dataclasses import replace
import json
import unittest
from fruitfly_agent.lab.context_manager.augmentation.memory.methods.file_memory.maintenance import ThresholdMaintenance
from fruitfly_agent.lab.context_manager.augmentation.memory.methods.file_memory.config import MaintenanceConfig
from fruitfly_agent.lab.catalog import ProviderBinding
from tests.support.faux_provider import FauxProvider
from tests.support.retained import memory


def checkpoint(text='user preference', *, chars=None, completed=True):
    return {'evidence': [{'identity': 'session-a:session:1', 'session_id': 'session-a',
        'message_id': 'session:1', 'chars': len(text) if chars is None else chars,
        'completed': completed, 'artifact': 'fixture'}], 'pending': {}, 'processed': 0, 'consolidated_turns': 0}


class MemoryMaintenanceTests(unittest.IsolatedAsyncioTestCase):
    def worker(self, provider, **overrides):
        return ThresholdMaintenance(replace(MaintenanceConfig(), **overrides), 'extract prompt', 'merge prompt',
            lambda: ProviderBinding(provider, 'fake', 'offline'))

    def test_only_new_user_characters_and_completed_turns_trigger(self):
        worker = self.worker(FauxProvider())
        state = checkpoint(chars=7999)
        self.assertIsNone(worker.request(state, '[]'))
        state['evidence'][0]['chars'] = 8000
        self.assertEqual('extract', worker.request(state, '[]')['operation'])
        state['processed'] = 1
        self.assertIsNone(worker.request(state, '[]'))
        state['evidence'] = [{**state['evidence'][0], 'chars': 1, 'identity': str(i)} for i in range(50)]
        state['processed'] = 50
        self.assertEqual('consolidate', worker.request(state, '[]')['operation'])
        state['consolidated_turns'] = 50
        state['processed'] = 50
        self.assertIsNone(worker.request(state, '[]'))

    async def test_empty_library_consolidation_uses_no_model(self):
        provider = FauxProvider(); worker = self.worker(provider, consolidate_after_user_turns=1)
        state = checkpoint()
        text, processed, turns = await worker.generate(worker.request(state, '[]'), state, lambda row: 'text')
        self.assertIsNone(text); self.assertEqual(1, turns); self.assertEqual([], provider.calls)

    async def test_unchanged_completed_consolidation_advances_turns_without_another_model_call(self):
        provider = FauxProvider(); provider.respond_text('[]')
        worker = self.worker(provider, consolidate_after_user_turns=1)
        state = checkpoint()
        documents = json.dumps([memory()])
        first = worker.request(state, documents)
        await worker.generate(first, state, lambda row: 'source')
        state['consolidated_turns'] = 1
        state['operations'] = {'done': {'status': 'completed', 'operation': 'consolidate',
                                       'request_id': first['request_id']}}
        state['evidence'].append({**state['evidence'][0], 'identity': 'second', 'message_id': 'second'})
        request = worker.request(state, documents)
        text, _, turns = await worker.generate(request, state, lambda row: 'source')
        self.assertIsNone(text)
        self.assertEqual(2, turns)
        self.assertEqual(1, len(provider.calls))
        changed = json.dumps([{**memory(), 'body': 'A changed retained fact.'}])
        self.assertFalse(worker.request(state, changed)['unchanged'])

    async def test_invalid_nonempty_output_cannot_replace_library(self):
        provider = FauxProvider(); provider.respond_text('[{}]')
        worker = self.worker(provider, extract_after_user_chars=1)
        state = checkpoint()
        documents = json.dumps([memory()])
        with self.assertRaises(ValueError):
            await worker.generate(worker.request(state, documents), state, lambda row: 'Prefer A.')
        self.assertEqual(0, state['processed'])

    async def test_no_change_still_advances_only_inspected_evidence(self):
        provider = FauxProvider(); provider.respond_text('[]')
        worker = self.worker(provider, extract_after_user_chars=1, max_input_chars=100)
        state = checkpoint()
        text, processed, turns = await worker.generate(worker.request(state, '[]'), state, lambda row: 'Prefer A.')
        self.assertIsNone(text); self.assertEqual(1, processed)
        self.assertEqual('extract prompt', provider.calls[0]['system_prompt'])
        self.assertEqual([], provider.calls[0]['tools'])

    async def test_oversized_single_message_is_fully_paged_before_processing_advances(self):
        provider = FauxProvider()
        for _ in range(4):
            provider.respond_text('[]')
        worker = self.worker(provider, extract_after_user_chars=1, max_input_chars=3)
        state = checkpoint()
        text, processed, _ = await worker.generate(worker.request(state, '[]'), state, lambda row: 'long input')
        self.assertIsNone(text)
        self.assertEqual(1, processed)
        pages = [json.loads(call['messages'][0].content)['evidence'][0] for call in provider.calls]
        self.assertEqual('long input', ''.join(page['text'] for page in pages))
        self.assertEqual(1, len({page['id'] for page in pages}))

    async def test_late_page_failure_leaves_checkpoint_untouched(self):
        provider = FauxProvider(); provider.respond_text('[]'); provider.respond_text('[{}]')
        worker = self.worker(provider, extract_after_user_chars=1, max_input_chars=3)
        state = checkpoint()
        with self.assertRaises(ValueError):
            await worker.generate(worker.request(state, '[]'), state, lambda row: 'abcdef')
        self.assertEqual(0, state['processed'])

    def test_pending_update_blocks_another_parent_conflicting_batch(self):
        state = checkpoint(chars=8000); state['pending']['update'] = {'status': 'pending'}
        self.assertIsNone(self.worker(FauxProvider()).request(state, '[]'))

    def test_consolidation_is_not_starved_when_both_thresholds_are_due(self):
        worker = self.worker(FauxProvider(), extract_after_user_chars=1, consolidate_after_user_turns=1)
        state = checkpoint()
        self.assertEqual('consolidate', worker.request(state, json.dumps([memory()]))['operation'])

    async def test_consolidation_visits_notes_after_the_first_page(self):
        provider = FauxProvider(); provider.respond_text('[]'); provider.respond_text('[]')
        worker = self.worker(provider, extract_after_user_chars=99999, consolidate_after_user_turns=1,
            max_input_chars=700)
        state = checkpoint()
        entries = [memory(), memory('memory-other')]
        result, processed, turns = await worker.generate(worker.request(state, json.dumps(entries)), state, lambda row: 'text')
        self.assertIsNone(result)
        seen = {entry['id'] for call in provider.calls for entry in json.loads(call['messages'][0].content)['memories']}
        self.assertEqual({e['id'] for e in entries}, seen)
        self.assertEqual(0, processed); self.assertEqual(1, turns)
