"""Explicit backend validation of frozen output files in a fresh working directory."""
import asyncio
import hashlib
from dataclasses import dataclass, asdict, replace
import os
from pathlib import Path
import signal
import tempfile
import time

from fruitfly_agent.improvement.contracts.execution import ExecutionRecord
from fruitfly_agent.improvement.contracts.failures import IntegrityError, StageFailure
from fruitfly_agent.improvement.contracts.tasks import Resource
from fruitfly_agent.improvement.contracts.versions import canonical_json
from fruitfly_agent.improvement.contracts.validation import identifier
from fruitfly_agent.improvement.execution.facts import read_facts, attach_facts, receipt_facts, FACTS_PATH
from fruitfly_agent.improvement.workflow.operations import run_stage, require_type
from ..execution.deliverables import DeliveryBundle


def validate_delivery_backend(backend):
    if not callable(getattr(backend, 'validate', None)):
        raise ValueError('delivery backend must implement validate')
    implementation = getattr(backend, 'implementation_id', None)
    if not isinstance(implementation, str):
        raise ValueError('delivery backend requires an implementation identity')
    identifier(implementation)
    configuration = getattr(backend, 'configuration', None)
    if not isinstance(configuration, dict):
        raise ValueError('delivery backend requires a configuration identity')
    canonical_json(configuration)


@dataclass(frozen=True)
class DeliveryResult:
    status: str
    exit_code: int | None
    stdout: str
    stderr: str
    elapsed_seconds: float
    bundle_id: str = ''

    def __post_init__(self):
        import math
        if (self.status not in {'passed', 'failed', 'unavailable', 'timeout'}
                or self.exit_code is not None and type(self.exit_code) is not int
                or not isinstance(self.stdout, str) or not isinstance(self.stderr, str)
                or max(len(self.stdout), len(self.stderr)) > 120000
                or not math.isfinite(self.elapsed_seconds) or self.elapsed_seconds < 0):
            raise ValueError('invalid delivery validation receipt')
        if self.status == 'passed' and self.exit_code != 0:
            raise ValueError('passing delivery needs a confirmed zero exit')


class CommandDeliveryBackend:
    """The host explicitly selects a command; this is process isolation, not an OS sandbox."""
    implementation_id = 'clean-directory-command-v1'

    def __init__(self, command):
        self.command = tuple(command)
        if not self.command or not Path(self.command[0]).is_absolute():
            raise ValueError('delivery backend requires an explicitly authorized absolute executable')

    @property
    def configuration(self):
        return {'command': list(self.command)}

    async def validate(self, bundle, artifacts):
        started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix='fruitfly-delivery-') as directory:
            root = Path(directory)
            for resource in bundle.files:
                data = artifacts.read(resource.artifact_id)
                if 'sha256:' + hashlib.sha256(data).hexdigest() != resource.artifact_id:
                    raise IntegrityError('delivery content identity mismatch')
                path = root / resource.path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            process = await asyncio.create_subprocess_exec(*self.command, bundle.spec.entrypoint,
                *bundle.spec.arguments, cwd=root, env={}, start_new_session=True,
                stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            async def capture(stream):
                retained = bytearray()
                while True:
                    part = await stream.read(8192)
                    if not part:
                        return bytes(retained).decode('utf-8', errors='replace')
                    retained.extend(part[:max(0, 120000 - len(retained))])
            outputs = [asyncio.create_task(capture(stream)) for stream in (process.stdout, process.stderr)]
            timed_out = False
            try:
                try:
                    await asyncio.wait_for(process.wait(), bundle.spec.timeout_seconds)
                except TimeoutError:
                    timed_out = True
                # Descendants must not retain pipes or outlive this validation.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await process.wait()
                stdout, stderr = await asyncio.wait_for(asyncio.gather(*outputs), 2)
            finally:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await process.wait()
                for task in outputs:
                    task.cancel()
                await asyncio.gather(*outputs, return_exceptions=True)
            passed = process.returncode == 0 and (not bundle.spec.require_stdout or bool(stdout.strip()))
            return DeliveryResult('timeout' if timed_out else 'passed' if passed else 'failed',
                process.returncode, stdout, stderr, time.monotonic() - started, bundle.bundle_id)


class DeliveryValidationRunner:
    def __init__(self, runner, spec, backend, artifacts, services):
        validate_delivery_backend(backend)
        self.runner, self.spec, self.backend = runner, spec, backend
        self.artifacts, self.services = artifacts, services
        self.capabilities = runner.capabilities | {'delivery-validation'}
        self.execution_charge = getattr(runner, 'execution_charge', 1)

    async def execute(self, plan, task, harness):
        record = await self.runner.execute(plan, task, harness)
        if not isinstance(record, ExecutionRecord):
            raise TypeError('delivery runner requires an execution receipt')
        if record.status != 'completed':
            return record
        bundle = None
        try:
            bundle = DeliveryBundle.collect(record, task, self.spec)
        except ValueError as exc:
            result = DeliveryResult('failed', None, '', str(exc), 0)
        else:
            try:
                result = await run_stage(self.services, 'delivery', lambda: self.backend.validate(bundle, self.artifacts),
                    validator=lambda value: require_type(value, DeliveryResult))
            except StageFailure:
                result = DeliveryResult('unavailable', None, '', 'Delivery backend did not return a complete receipt.', 0, bundle.bundle_id)
            if result.bundle_id != bundle.bundle_id:
                raise IntegrityError('delivery receipt belongs to a different bundle')
            if result.status == 'passed' and self.spec.require_stdout and not result.stdout.strip():
                result = replace(result, status='failed')
        value = {'result': asdict(result), 'bundle': asdict(bundle) if bundle else None,
                 'backend': {'implementation': self.backend.implementation_id, 'configuration': self.backend.configuration}}
        reference = self.artifacts.put(canonical_json(value).encode())
        self.services.record('delivery-validation', run_id=record.run_id, artifact_id=reference, status=result.status)
        previous = read_facts(record, self.artifacts)
        artifacts = tuple(r for r in record.artifacts if r.path != FACTS_PATH)
        record = replace(record, status='completed' if result.status == 'passed' else 'error',
            artifacts=(*artifacts, Resource('delivery-validation.json', reference, 'application/json', 'diagnostic')))
        facts = receipt_facts(record, self.artifacts, complete=True, diagnosable=True,
            termination_reason='delivery_' + result.status)
        if previous is not None:
            facts = replace(facts, counters=previous.counters, budgets=previous.budgets, elapsed_seconds=previous.elapsed_seconds)
        return attach_facts(record, facts, self.artifacts)
