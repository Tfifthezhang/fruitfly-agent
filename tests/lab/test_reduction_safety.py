"""Working-memory invalid output, coverage, budget and tool-link safety."""
from dataclasses import replace
import unittest
from fruitfly_agent.core.data_model import AssistantMessage, ContextItem, ContextSnapshot, TextBlock, ToolCallBlock, ToolResultMessage, UserMessage, CustomMessage, ImageBlock
from fruitfly_agent.lab.context_manager.reduction import WorkingMemoryConfig, WorkingMemoryReducer
from fruitfly_agent.lab.context_manager.reduction.cut import find_cut_point, valid_tool_links
from tests.support.faux_provider import FauxProvider


def snapshot(messages=None, **overrides):
    messages = tuple(messages or (UserMessage('task'), AssistantMessage([TextBlock('evidence ' + 'x' * 4000)]), UserMessage('correction')))
    values = dict(messages=messages, canonical_items=tuple(ContextItem(str(i), m) for i, m in enumerate(messages)),
        system_prompt='', tools=(), context_window=512, model='fake', max_tokens=32, trigger='budget')
    values.update(overrides)
    return ContextSnapshot(**values)


def reducer(provider, **changes):
    return WorkingMemoryReducer(WorkingMemoryConfig(memory_tokens=64, auxiliary_attempts=1, auxiliary_max_tokens=128, **changes), provider)


class ReductionSafetyTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_blank_truncated_error_and_tool_outputs_without_changing_source(self):
        original = snapshot(); before = [m.to_dict() for m in original.messages]
        for response in (AssistantMessage([TextBlock(' ')], stop_reason='stop'),
                AssistantMessage([TextBlock('memory')], stop_reason='length'),
                AssistantMessage([TextBlock('memory')], stop_reason='stop', continue_turn=True),
                AssistantMessage([TextBlock('memory')], stop_reason='error'),
                AssistantMessage([ToolCallBlock('call', 'write', {})], stop_reason='stop')):
            with self.subTest(response=response):
                provider = FauxProvider(); provider.respond(response)
                self.assertIsNone(await reducer(provider).check_budget(original))
                self.assertEqual(before, [m.to_dict() for m in original.messages])

    async def test_oversized_memory_and_failed_shortening_never_commit(self):
        provider = FauxProvider(); provider.respond_text('x' * 1000); provider.respond_text('x' * 1000)
        original = snapshot()
        self.assertIsNone(await reducer(provider).check_budget(original))
        self.assertEqual({}, original.context_state)

    async def test_fitting_projection_preserves_original_task_and_canonical_corrections_in_memory_input(self):
        provider = FauxProvider(); provider.respond_text('task; correction; pending verification')
        method = reducer(provider); original = snapshot()
        decision = await method.check_budget(original)
        self.assertIsNotNone(decision.messages)
        self.assertEqual(original.messages[0], decision.messages[-1])
        self.assertIn('correction', provider.calls[0]['messages'][0].content)
        self.assertLess(method.estimate(replace(original, messages=decision.messages)), original.context_window - original.max_tokens)
        self.assertEqual(len(original.canonical_items), decision.state['covered'])

    async def test_invalid_or_pending_tool_links_do_not_start_auxiliary_work(self):
        for messages in ((UserMessage('task'), ToolResultMessage('missing', [TextBlock('result')])),
                (UserMessage('task'), AssistantMessage([ToolCallBlock('c', 'read', {})]), UserMessage('steering'))):
            provider = FauxProvider()
            self.assertIsNone(await reducer(provider).check_budget(snapshot(messages)))
            self.assertEqual([], provider.calls)

    async def test_failed_page_can_be_retried_without_permanent_suppression(self):
        provider = FauxProvider(); method = reducer(provider)
        provider.respond_text(' ')
        self.assertIsNone(await method.check_budget(snapshot()))
        provider.respond_text('memory')
        self.assertIsNotNone((await method.check_budget(snapshot())).messages)

    async def test_auxiliary_model_capacity_limits_each_page_and_preserves_every_character(self):
        provider = FauxProvider()
        for _ in range(100): provider.respond_text('bounded memory')
        method = WorkingMemoryReducer(WorkingMemoryConfig(memory_tokens=64, auxiliary_max_tokens=64,
            page_char_limit=100, max_pages=128), provider, memory_context_window=1024, memory_output_limit=32)
        result = await method.check_budget(snapshot())
        self.assertEqual(len(snapshot().canonical_items), result.state['covered'])
        pages = [c['messages'][0].content.split('<evidence>\n')[1].split('\n</evidence>')[0] for c in provider.calls]
        self.assertIn('x' * 4000, ''.join(pages))
        self.assertTrue(all(c['max_tokens'] == 32 for c in provider.calls))
        self.assertTrue(all(method.meter.text_tokens(c['system_prompt'] + c['messages'][0].content) + 32 < 1024 for c in provider.calls))

    async def test_canonical_public_sources_keep_errors_and_omit_image_bytes(self):
        provider = FauxProvider(); provider.respond_text('memory')
        messages = (CustomMessage('compactionSummary', 'prior decisions'),
            UserMessage([TextBlock('constraint'), ImageBlock('base64-secret', 'image/png')]),
            AssistantMessage([ToolCallBlock('c', 'write', {'path': 'important.txt'})]),
            ToolResultMessage('c', [TextBlock('failed ' + 'x' * 4000)], is_error=True))
        await reducer(provider).check_budget(snapshot(messages))
        prompt = provider.calls[0]['messages'][0].content
        for text in ('prior decisions', 'constraint', 'image/png', 'important.txt', 'error=True'): self.assertIn(text, prompt)
        self.assertNotIn('base64-secret', prompt)

    def test_steering_boundary_cannot_split_a_tool_pair(self):
        messages = [UserMessage('old'), AssistantMessage([TextBlock('answer')]), UserMessage('task'),
            AssistantMessage([ToolCallBlock('c', 'read', {})]), UserMessage('steering'), ToolResultMessage('c', [TextBlock('result')])]
        cut = find_cut_point(messages, 1, lambda _: 1)
        self.assertEqual(2, cut)
        self.assertTrue(valid_tool_links(messages[cut:]))
