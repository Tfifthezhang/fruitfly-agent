"""Eval controller process ownership and evidence forwarding stay offline."""
import asyncio
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from eval.improvement.process import EvalProcess
from eval.contracts import EvaluationRequest


class EvalProcessTests(unittest.IsolatedAsyncioTestCase):
    def request(self, root):
        return EvaluationRequest.from_dict({'runtime': {'working_directory': str(root)},
            'benchmark': {'id': 'terminal-bench-4', 'variant': 'smoke'}})

    async def test_only_lifecycle_progress_is_forwarded_and_full_output_is_logged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); output = root / 'eval'; target = output / 'evaluation'; target.mkdir(parents=True)
            report = {'evaluation_id': 'evaluation', 'status': 'completed'}
            (target / 'report.json').write_text(json.dumps(report))
            process = SimpleNamespace(returncode=None, terminate=Mock(), kill=Mock())
            async def wait(): process.returncode = 0; return 0
            process.wait = AsyncMock(side_effect=wait)
            process.stdout = SimpleNamespace(readline=AsyncMock(side_effect=[
                b'{"type":"started","evaluation_id":"evaluation"}\n',
                b'{"type":"log","text":"PRIVATE_TEST_OUTPUT"}\n', b'']))
            events = []
            with patch('eval.improvement.process.asyncio.create_subprocess_exec', AsyncMock(return_value=process)) as spawn:
                actual, path = await EvalProcess()(self.request(root), root / 'host.yaml',
                    directory=root, output_root=output, emit=lambda *args, **fields: events.append((args, fields)))
            self.assertEqual(actual, report); self.assertEqual(path, target)
            self.assertEqual(events, [(('benchmark-progress',), {'event_type': 'started'})])
            self.assertIn('PRIVATE_TEST_OUTPUT', (root / 'controller.log').read_text())
            self.assertIn('run', spawn.call_args.args)
            process.terminate.assert_not_called()

    async def test_cancellation_during_spawn_retires_the_created_process(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); entered, release = asyncio.Event(), asyncio.Event()
            process = SimpleNamespace(returncode=None, terminate=Mock(), kill=Mock())
            async def wait(): process.returncode = -15; return -15
            process.wait = AsyncMock(side_effect=wait)
            async def spawn(*args, **kwargs):
                entered.set(); await release.wait(); return process
            with patch('eval.improvement.process.asyncio.create_subprocess_exec', spawn):
                pending = asyncio.create_task(EvalProcess()(self.request(root), root / 'host.yaml',
                    directory=root, output_root=root / 'eval', emit=lambda *args, **kwargs: None))
                await entered.wait(); pending.cancel(); await asyncio.sleep(0); release.set()
                with self.assertRaises(asyncio.CancelledError): await pending
            process.terminate.assert_called_once()
            process.wait.assert_awaited_once()
