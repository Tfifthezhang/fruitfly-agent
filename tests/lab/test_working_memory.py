"""Incremental coverage, transactional checkpoints and recovery; no model network."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.data_model import (ContextItem, ContextSnapshot, UserMessage, AssistantMessage,
    ToolCallBlock, ToolResultMessage, TextBlock)
from fruitfly_agent.core.loop import run_agent_loop
from fruitfly_agent.core.session import Session
from fruitfly_agent.core.context_runtime import restore_context_state
from fruitfly_agent.lab.context_manager.history import SessionHistory
from fruitfly_agent.lab.context_manager.reduction.methods.working_memory.algorithm import WorkingMemoryReducer
from fruitfly_agent.lab.context_manager.reduction.methods.working_memory.config import WorkingMemoryConfig
from fruitfly_agent.lab.context_manager.measurement.budget import MeasurementService, MeasurementConfig
from tests.support.faux_provider import FauxProvider


def snapshot(messages=None, **changes):
    messages = tuple(messages or (UserMessage('Complete the task; verify the output'),
        AssistantMessage([TextBlock('evidence ' + 'x' * 4000)])))
    data = dict(canonical_items=tuple(ContextItem(str(i), m) for i, m in enumerate(messages)),
        messages=messages, system_prompt='', tools=(), context_window=1024, model='fake', max_tokens=32, trigger='budget')
    data.update(changes)
    return ContextSnapshot(**data)


def reducer(provider, history=None, **changes):
    return WorkingMemoryReducer(WorkingMemoryConfig(memory_tokens=64, auxiliary_max_tokens=128,
        update_every_messages=1, **changes), provider, history=history)


class WorkingMemoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_updates_only_new_evidence_and_keeps_code_owned_coverage(self):
        provider = FauxProvider(); provider.respond_text('step one complete'); provider.respond_text('step two pending')
        method = reducer(provider)
        first = snapshot([UserMessage('task'), AssistantMessage([TextBlock('first evidence')])])
        decision = await method.check_budget(first)
        self.assertIsNone(decision.messages)
        self.assertEqual(2, decision.state['covered'])
        added = (*first.messages, UserMessage('new correction'))
        second = snapshot(added, context_state={method.mechanism_id: decision.state})
        updated = await method.check_budget(second)
        prompt = provider.calls[-1]['messages'][0].content
        self.assertIn('step one complete', prompt)
        self.assertIn('new correction', prompt)
        self.assertNotIn('first evidence', prompt)
        self.assertEqual(3, updated.state['covered'])
        self.assertEqual(2, decision.state['covered'])

    async def test_partial_coverage_never_clears_context_and_resumes_exact_character(self):
        provider = FauxProvider()
        for _ in range(100): provider.respond_text('bounded memory')
        method = reducer(provider, page_char_limit=100, max_pages=1)
        current = snapshot()
        pages = []
        first = None
        for _ in range(100):
            decision = await method.check_budget(current)
            self.assertIsNotNone(decision)
            if first is None: first = decision
            prompt = provider.calls[-1]['messages'][0].content
            pages.append(prompt.split('<evidence>\n', 1)[1].split('\n</evidence>', 1)[0])
            if decision.messages is not None:
                break
            self.assertLess(decision.state['covered'], len(current.canonical_items))
            current = replace(current, context_state={method.mechanism_id: decision.state})
        else: self.fail('coverage did not finish within the bounded source size')
        self.assertIn('x' * 4000, ''.join(pages))
        self.assertEqual(len(current.canonical_items), decision.state['covered'])
        self.assertEqual(0, decision.state['offset'])
        self.assertEqual(2, len(decision.messages))
        self.assertIsNone(first.messages)
        self.assertLess(method.estimate(replace(current, messages=decision.messages)), current.context_window - current.max_tokens)

    async def test_failed_page_and_oversize_shortening_preserve_previous_checkpoint(self):
        provider = FauxProvider(); provider.respond_text('valid memory')
        method = reducer(provider, page_char_limit=100, max_pages=1)
        original = snapshot()
        checkpoint = (await method.check_budget(original)).state
        current = replace(original, context_state={method.mechanism_id: checkpoint})
        for final in ('', 'a' * 1000):
            provider.respond_text(final); provider.respond_text('b' * 1000)
            self.assertIsNone(await method.check_budget(current))
            self.assertEqual(checkpoint, current.context_state[method.mechanism_id])
            provider.script.clear()

    async def test_invalid_model_output_and_signal_never_commit(self):
        for reason in ('length', 'error'):
            provider = FauxProvider(); provider.respond_text('memory', stop_reason=reason)
            self.assertIsNone(await reducer(provider).check_budget(snapshot()))
        import asyncio
        signal = asyncio.Event(); signal.set()
        with self.assertRaises(asyncio.CancelledError):
            await reducer(FauxProvider()).check_budget(snapshot(signal=signal))

    async def test_mismatched_source_is_rejected_and_changed_policy_rebuilds(self):
        provider = FauxProvider(); provider.respond_text('old memory'); provider.respond_text('new memory')
        method = reducer(provider)
        source = snapshot([UserMessage('original')])
        checkpoint = (await method.check_budget(source)).state
        wrong = snapshot([UserMessage('different')], context_state={method.mechanism_id: checkpoint})
        with self.assertRaisesRegex(ValueError, 'source coverage'):
            await method.check_budget(wrong)
        changed = reducer(provider, update_instructions='Candidate policy')
        decision = await changed.check_budget(replace(source, context_state={method.mechanism_id: checkpoint}))
        self.assertIn('original', provider.calls[-1]['messages'][0].content)
        self.assertNotIn('old memory', provider.calls[-1]['messages'][0].content)
        self.assertNotEqual(checkpoint['policy'], decision.state['policy'])

    async def test_session_commit_recovery_corruption_and_task_isolation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'session.jsonl'; root = Path(directory) / 'objects'
            with Session(path) as session:
                provider = FauxProvider(); provider.respond_text('done')
                auxiliary = FauxProvider(); auxiliary.respond_text('verified progress; next verify output')
                history = SessionHistory(root, session=session)
                method = reducer(auxiliary, history)
                config = AgentLoopConfig(provider, session=session, context_window=1024, max_tokens=32,
                    context_meter=MeasurementService(MeasurementConfig(margin_tokens=0, margin_ratio=0)))
                result = await run_agent_loop(config, list(snapshot().messages), context_pipeline=method)
                self.assertFalse(result.is_error, result.error_details)
                saved = restore_context_state(session)[method.mechanism_id]
                self.assertEqual(2, saved['covered'])
                self.assertTrue(any(e.type == 'compaction' and e.payload.get('state') == saved for e in session.read_all()))
            with Session(path) as session:
                recovered = reducer(FauxProvider(), SessionHistory(root, session=session))
                recovered.validate_recovery(session.messages())
                reference = saved['artifact']
                self.assertEqual('verified progress; next verify output', recovered.history.text(reference))
                other = reducer(FauxProvider(), SessionHistory())
                with self.assertRaises(KeyError): other.history.text(reference)
                artifact = root / (reference[7:] + '.txt')
                artifact.write_text('tampered')
                with self.assertRaisesRegex(ValueError, 'identity'):
                    recovered.validate_recovery(session.messages())
                artifact.unlink()
                with self.assertRaises(FileNotFoundError): recovered.validate_recovery(session.messages())

    async def test_signed_projection_can_update_state_but_cannot_reset(self):
        provider = FauxProvider(); provider.respond_text('new memory')
        method = reducer(provider)
        original = snapshot(rebase_allowed=False)
        decision = await method.check_budget(original)
        self.assertIsNone(decision.messages)
        self.assertIsNotNone(decision.state)
        self.assertIsNone(await method.react_to_overflow(replace(original, context_state={method.mechanism_id: decision.state}), RuntimeError()))

    async def test_pending_tool_pair_is_never_summarized(self):
        provider = FauxProvider()
        messages = [UserMessage('task'), AssistantMessage([ToolCallBlock('call', 'read', {})])]
        self.assertIsNone(await reducer(provider).check_budget(snapshot(messages)))
        self.assertEqual([], provider.calls)
