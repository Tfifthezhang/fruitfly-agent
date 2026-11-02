"""Default deterministic projection, original evidence and source-safe decisions."""
from copy import deepcopy
from dataclasses import replace
import json
import unittest

from fruitfly_agent.core.context.validation import valid_tool_links
from fruitfly_agent.core.data_model import ToolResultMessage, CustomMessage
from fruitfly_agent.lab.context_manager.reduction import LayeredCompactionReducer, LayeredCompactionConfig
from tests.support.compaction import mounted_history, source_messages, snapshot


class LayeredCompactionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.history, self.resources = mounted_history()
        self.addCleanup(self.resources.close)

    def reducer(self, **values):
        return LayeredCompactionReducer(LayeredCompactionConfig(**values), history=self.history)

    async def test_small_requests_do_not_create_checkpoints_or_invoke_inference(self):
        from fruitfly_agent.core.data_model import UserMessage
        method = self.reducer()
        self.assertIsNone(await method.check_budget(snapshot([UserMessage('hello')])))
        self.assertEqual(self.history.values, {})

    async def test_old_tool_results_are_abbreviated_without_changing_originals_or_pairing(self):
        messages = source_messages(tools=True)
        original = deepcopy([m.to_dict() for m in messages])
        method = self.reducer(preview_chars=128, tool_result_min_chars=256, keep_recent_groups=1)
        source = snapshot(messages, context_window=100000)
        decision = await method.check_budget(source)
        self.assertIsNotNone(decision.messages)
        self.assertTrue(valid_tool_links(decision.messages))
        self.assertEqual(original, [m.to_dict() for m in messages])
        reduced = [m for m in decision.messages if isinstance(m, ToolResultMessage)]
        self.assertEqual(len(reduced), 8)
        self.assertTrue(reduced[2].is_error)
        reference = reduced[2].text.split('Original result: ')[1]
        self.assertIn(b'Original result 2', self.resources.read(reference))
        self.assertLess(method.estimate(replace(source, messages=decision.messages)), method.estimate(source))
        self.assertEqual(self.history.values, {})

    async def test_history_archive_keeps_task_current_input_and_original_readback(self):
        messages = source_messages()
        method = self.reducer(keep_recent_groups=1, tail_tokens=256)
        source = snapshot(messages)
        decision = await method.check_budget(source)
        self.assertIsNotNone(decision.messages)
        self.assertIn(messages[0], decision.messages)
        self.assertIn(messages[-1], decision.messages)
        note = next(m for m in decision.messages if isinstance(m, CustomMessage))
        self.assertIn('History index:', note.text)
        index = json.loads(self.resources.read(self.history.resource_prefix+'index'))
        self.assertEqual(len(index['messages']), len(messages))
        self.assertIn(b'Correction 2', self.resources.read(index['messages'][6]['reference']))
        self.assertTrue(decision.state['artifacts'])
        self.assertLess(method.estimate(replace(source, messages=decision.messages)), source.context_window-source.max_tokens)
        # Current projected state is reused rather than restoring archived verbosity.
        self.assertIsNone(await method.check_budget(replace(source, messages=decision.messages,
            context_state={method.mechanism_id:decision.state}, revision=1)))

    async def test_pending_calls_and_signed_continuation_cannot_be_rebased(self):
        from fruitfly_agent.core.data_model import AssistantMessage, ToolCallBlock
        method = self.reducer()
        for source in (snapshot(source_messages(), rebase_allowed=False),
                       snapshot([AssistantMessage([ToolCallBlock('pending','read',{})])])):
            with self.subTest(source=source):
                self.assertIsNone(await method.react_to_overflow(source, RuntimeError()))
        self.assertEqual(self.history.values, {})

    async def test_changed_source_checkpoint_is_rejected(self):
        method = self.reducer(keep_recent_groups=1, tail_tokens=256)
        source = snapshot(source_messages())
        decision = await method.check_budget(source)
        broken = {**decision.state, 'source_hash':'0'*64}
        with self.assertRaisesRegex(ValueError,'source identity'):
            await method.check_budget(replace(source, context_state={method.mechanism_id:broken}))

    async def test_missing_corrupt_and_malformed_active_dependencies_reject_recovery(self):
        method = self.reducer(keep_recent_groups=1, tail_tokens=256)
        source = snapshot(source_messages())
        decision = await method.check_budget(source)
        reference = decision.state['artifacts'][0]
        original = self.history.values.pop(reference)
        with self.assertRaises(KeyError): method.validate_recovery(decision.messages)
        self.history.values[reference] = b'corrupt'
        with self.assertRaisesRegex(ValueError, 'identity'): method.validate_recovery(decision.messages)
        self.history.values[reference] = original
        method.validate_recovery(decision.messages)
        with self.assertRaisesRegex(ValueError, 'dependencies'):
            await method.check_budget(replace(source, context_state={method.mechanism_id:
                {**decision.state, 'artifacts': [{}]}}))

    async def test_force_reports_retry_only_for_a_fitting_smaller_projection(self):
        method = self.reducer(keep_recent_groups=1, tail_tokens=256)
        decision = await method.react_to_overflow(snapshot(source_messages()), RuntimeError())
        self.assertTrue(decision.retry)
        self.assertTrue(valid_tool_links(decision.messages))

    def test_configuration_rejects_unknown_modes_invalid_limits_and_cross_field_conflicts(self):
        for values in ({'mode':'periodic'}, {'preview_chars':True}, {'trigger_ratio':float('nan')},
                       {'target_ratio':.8}, {'summary_target_tokens':8192,'summary_max_output_tokens':512},
                       {'summary_timeout_seconds':0}, {'readback_instructions':' '}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                LayeredCompactionConfig(**values)
