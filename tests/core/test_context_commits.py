"""Core validates final projections and persists state before replacing live context."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.context.budget import InputMeasurement
from fruitfly_agent.core.data_model import ContextDecision, CustomMessage, UserMessage
from fruitfly_agent.core.extensions.hooks import HookRegistry, BEFORE_COMPACTION
from fruitfly_agent.core.loop import run_agent_loop
from fruitfly_agent.core.session import Session
from fruitfly_agent.core.context_runtime import restore_context_state
from tests.support.faux_provider import FauxProvider


class Meter:
    async def measure(self, view, provider, *, signal=None):
        return InputMeasurement(sum(len(getattr(m, 'text', '') or getattr(m, 'content', '')) for m in view.messages),
            'offline-character-fixture', 'heuristic', 'fixture', view.max_tokens)


class Reducer:
    def __init__(self, *, state_only=False): self.state_only = state_only
    def estimate(self, snapshot): return 10
    async def check_budget(self, snapshot):
        return ContextDecision(messages=None if self.state_only else (CustomMessage('compactionSummary', 'memory'),),
            mechanism_id='fixture', state={'cursor': 1}, base_revision=snapshot.revision)
    async def react_to_overflow(self, snapshot, error): return None


class ContextCommitTests(unittest.IsolatedAsyncioTestCase):
    async def test_persistence_failure_preserves_both_projection_and_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory, Session(Path(directory) / 'session.jsonl') as session:
            provider = FauxProvider(); provider.respond_text('done')
            append = session.append
            def failing(kind, *args, **kwargs):
                if kind == 'compaction': raise OSError('offline disk failure')
                return append(kind, *args, **kwargs)
            config = AgentLoopConfig(provider, session=session, max_tokens=32)
            with patch.object(session, 'append', side_effect=failing):
                result = await run_agent_loop(config, [UserMessage('original task')], context_pipeline=Reducer())
            self.assertTrue(result.is_error)
            self.assertEqual('context_commit_unconfirmed', result.error_details['kind'])
            self.assertEqual([], provider.calls)
            self.assertEqual('original task', result.messages[0].content)
            self.assertEqual({}, restore_context_state(session))
            self.assertEqual([], [entry for entry in session.read_all() if entry.type == 'compaction'])

    async def test_state_only_commit_restores_without_changing_projection_or_running_compaction_hook(self):
        with tempfile.TemporaryDirectory() as directory, Session(Path(directory) / 'session.jsonl') as session:
            provider = FauxProvider(); provider.respond_text('done')
            hooks = HookRegistry(); observed = []
            hooks.add(BEFORE_COMPACTION, lambda event: observed.append(event))
            result = await run_agent_loop(AgentLoopConfig(provider, session=session, hooks=hooks),
                [UserMessage('original task')], context_pipeline=Reducer(state_only=True))
            self.assertFalse(result.is_error)
            self.assertEqual('original task', result.messages[0].content)
            self.assertEqual({'fixture': {'cursor': 1}}, restore_context_state(session))
            self.assertEqual([], observed)

    async def test_final_hook_cannot_inject_oversized_or_orphaned_projection(self):
        from fruitfly_agent.core.data_model import ToolResultMessage, TextBlock
        for value in ([CustomMessage('compactionSummary', 'x' * 4000)],
                      [ToolResultMessage('missing', [TextBlock('invalid')])]):
            hooks = HookRegistry()
            hooks.add(BEFORE_COMPACTION, lambda event: replace(event, messages=value))
            provider = FauxProvider(); provider.respond_text('done')
            result = await run_agent_loop(AgentLoopConfig(provider, hooks=hooks, context_meter=Meter(),
                context_window=100, max_tokens=10), [UserMessage('original task')], context_pipeline=Reducer())
            self.assertFalse(result.is_error, result.error_details)
            self.assertEqual('original task', provider.calls[0]['messages'][0].content)

    async def test_preflight_overflow_never_spends_a_provider_attempt(self):
        provider = FauxProvider()
        result = await run_agent_loop(AgentLoopConfig(provider, context_meter=Meter(), context_window=10, max_tokens=5),
            [UserMessage('oversized request')])
        self.assertTrue(result.is_error)
        self.assertEqual('context_overflow', result.error_details['kind'])
        self.assertEqual([], provider.calls)
        self.assertEqual(0, result.diagnostics.provider_attempts)
        self.assertEqual(0, result.diagnostics.provider_failures)

    async def test_stale_snapshot_rejected_after_compaction_hook(self):
        provider = FauxProvider(); provider.respond_text('done')
        current = []
        def prepare(ctx):
            current.append(ctx)
            return []
        def change(event): current[0].revision += 1
        hooks = HookRegistry(); hooks.add(BEFORE_COMPACTION, change)
        result = await run_agent_loop(AgentLoopConfig(provider, hooks=hooks, get_steering_messages=prepare),
            [UserMessage('original task')], context_pipeline=Reducer())
        self.assertFalse(result.is_error)
        self.assertEqual('original task', result.messages[0].content)

    async def test_fsync_failure_blocks_writer_and_model_until_reopened_without_duplicate_ids(self):
        from fruitfly_agent.core.errors import SessionCorruptError
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'session.jsonl'
            provider = FauxProvider(); provider.respond_text('done after recovery')
            with Session(path) as session:
                config = AgentLoopConfig(provider, session=session)
                with patch('fruitfly_agent.core.session.storage.os.fsync', side_effect=OSError('offline fsync failure')):
                    result = await run_agent_loop(config, [UserMessage('original task')], context_pipeline=Reducer())
                self.assertTrue(result.is_error)
                self.assertEqual('context_commit_unconfirmed', result.error_details['kind'])
                self.assertEqual([], provider.calls)
                persisted = path.read_bytes()
                with self.assertRaises(SessionCorruptError): session.append('meta', {'test': True})
                blocked = await run_agent_loop(config, result.messages)
                self.assertTrue(blocked.is_error)
                self.assertEqual('session_write_failed', blocked.error_details['kind'])
                self.assertEqual([], provider.calls)
                self.assertEqual(persisted, path.read_bytes())
            with Session(path) as recovered:
                entries = recovered.read_all()
                self.assertEqual(list(range(1, len(entries) + 1)), [entry.id for entry in entries])
                self.assertEqual({'fixture': {'cursor': 1}}, restore_context_state(recovered))
                result = await run_agent_loop(replace(config, session=recovered), recovered.messages())
                self.assertFalse(result.is_error)
                self.assertEqual(1, len(provider.calls))
