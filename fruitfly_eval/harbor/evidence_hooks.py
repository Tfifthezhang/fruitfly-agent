"""Bind public Harbor job hooks to per-trial installed capture capabilities."""
from dataclasses import dataclass
import asyncio
import json
import logging
from pathlib import Path
import shlex
from typing import Any, Awaitable, Callable
from .evidence_capture import capture_policy
from .material import write_json


@dataclass
class CaptureBinding:
    python: str
    policy: dict
    execute: Callable[[str, int], Awaitable[Any]]
    download: Callable[[Path], Awaitable[Any]]
    forbidden: tuple
    stage: int = 0


# Ephemeral owned capabilities, not an algorithm/configuration registry. Install
# supplies the environment capability; trial end releases it. No Harbor internals.
_bindings: dict[Path, CaptureBinding] = {}


def bind_capture(trial_directory, *, python, policy, execute, download, forbidden=()):
    _bindings[Path(trial_directory).resolve()] = CaptureBinding(
        python, capture_policy(policy), execute, download, tuple(forbidden))


class EvidenceCapturePlugin:
    async def on_job_start(self, job):
        job.on_agent_started(self.baseline)
        job.on_agent_ended(self.final)
        job.on_trial_ended(self.release)
        job.on_trial_cancelled(self.release)
        self.root = Path(job.job_dir).resolve()

    async def on_job_end(self, job_result):
        for path in tuple(_bindings):
            if path.is_relative_to(self.root):
                del _bindings[path]

    async def release(self, event):
        _bindings.pop(self.directory(event), None)

    @staticmethod
    def directory(event):
        return (Path(event.config.trials_dir) / event.config.trial_name).resolve()

    async def baseline(self, event):
        binding = _bindings.get(self.directory(event))
        if binding:
            binding.stage += 1
        await self.capture(event, 'baseline')

    async def final(self, event):
        await self.capture(event, 'final')

    async def capture(self, event, phase):
        directory = self.directory(event)
        target = directory / 'agent/evidence-capture'
        binding = _bindings.get(directory)
        try:
            if binding is None:
                raise ValueError('installed capture capability unavailable')
            seconds = binding.policy['baseline_seconds' if phase == 'baseline' else 'capture_seconds']
            command = shlex.join([binding.python, '-P', '-m', 'fruitfly_eval.harbor.evidence_capture',
                '--phase', phase, '--policy', json.dumps(binding.policy), '--stage', str(binding.stage),
                '--destination', '/logs/agent/evidence-capture', '--forbidden', json.dumps(binding.forbidden)])
            result = await asyncio.wait_for(binding.execute(command, seconds + 5), seconds + 10)
            if result.return_code != 0:
                raise RuntimeError('capture command failed')
            await asyncio.wait_for(binding.download(target), seconds + 10)
        except Exception as exc:
            try:
                target.mkdir(parents=True, exist_ok=True)
                write_json(target / ('manifest.json' if phase == 'final' else 'baseline.json'), {
                    'schema_version': 1, 'status': 'partial', 'phase': phase,
                    'files': [], 'reason': type(exc).__name__, 'detail': str(exc)[:500]})
            except OSError:
                logging.getLogger(__name__).warning('Evidence capture receipt unavailable: %s', type(exc).__name__)
