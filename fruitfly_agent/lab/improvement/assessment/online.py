"""Bounded online assessment over immutable committed events."""
from dataclasses import asdict, replace
import asyncio
from uuid import uuid4

from fruitfly_agent.improvement.contracts.live import Assessment
from fruitfly_agent.improvement.contracts.execution import ExecutionRecord
from fruitfly_agent.improvement.contracts.tasks import Resource
from fruitfly_agent.improvement.contracts.versions import canonical_json
from fruitfly_agent.improvement.execution.handles import CompletionOnlyRunner
from fruitfly_agent.improvement.workflow.budget import AllocationExhausted


class AssessedRunner:
    """Wrap any backend without starting a second Agent loop.

    Assessors are fresh per execution. Events persist while judges run. Controls
    are opt-in, capability checked, and attributed. No implicit feedback exists.
    """
    def __init__(self, runner, *, artifacts, services, assessors, control_policy=None,
                 interval=1, assessor_timeout=30):
        if type(interval) is not int or interval < 1 or assessor_timeout <= 0:
            raise ValueError('online assessment requires bounded scheduling')
        self.runner, self.artifacts, self.services = runner, artifacts, services
        self.assessor_factories = tuple(assessors)
        self.control_policy, self.interval, self.assessor_timeout = control_policy, interval, assessor_timeout
        self.capabilities = runner.capabilities
        self.execution_charge = getattr(runner, 'execution_charge', 1)

    async def execute(self, plan, task, harness):
        backend = self.runner if callable(getattr(self.runner, 'start', None)) else CompletionOnlyRunner(
            self.runner, self.artifacts, self.services.record)
        handle = None
        assessors = []
        receipts: list[str] = []
        last: dict[str, str] = {}
        event_refs: list[str] = []
        try:
            for factory in self.assessor_factories:
                assessors.append(self.services.own(factory()))
            handle = await backend.start(plan, task, harness)
            async for event in handle.events():
                self.services.check()
                event_refs.append(self.artifacts.put(canonical_json(asdict(event)).encode()))
                for assessor in assessors:
                    observe = getattr(assessor, 'observe', None)
                    if observe is not None:
                        observe(event)
                final = event.kind in {'finished', 'failed', 'cancelled'}
                if event.position.sequence % self.interval and not final:
                    continue
                for assessor in assessors:
                    try:
                        value = await self.services.operation(asyncio.wait_for(
                            assessor.assess(event), timeout=self.assessor_timeout))
                        if value is None:
                            continue
                        if value.position != event.position or value.assessor_id != assessor.assessor_id:
                            raise ValueError('online assessment has mismatched evidence or scorer')
                        previous = last.get(assessor.assessor_id, '')
                        value = replace(value, supersedes=previous)
                    except asyncio.CancelledError:
                        raise
                    except AllocationExhausted:
                        raise
                    except Exception as exc:
                        value = Assessment(event.position, assessor.assessor_id, (), status='failed',
                            scope='execution' if final else 'prefix', detail=type(exc).__name__)
                    ref = self.artifacts.put(canonical_json(asdict(value)).encode())
                    receipts.append(ref)
                    last[assessor.assessor_id] = value.assessment_id
                    self.services.record('online-assessment', evidence=ref, status=value.status,
                        assessor_id=value.assessor_id, sequence=event.position.sequence)
                    if not final and self.control_policy is not None and value.visibility == 'development' and value.status not in {'failed', 'unavailable', 'incomplete'}:
                        requests = await self.services.operation(self.control_policy.decide(value))
                        for request in requests:
                            await handle.control(request)
            try:
                result = await handle.result()
            except asyncio.CancelledError:
                if not getattr(handle, 'stopped', False) or self.services.signal.is_set():
                    raise
                result = ExecutionRecord('stopped-' + uuid4().hex, task.task_id, task.material_id,
                    harness.snapshot_id, plan.parent.state, plan.conditions_id, 'cancelled')
            index = self.artifacts.put(canonical_json({'schema_version': 1, 'assessments': receipts,
                'events': event_refs}).encode())
            return replace(result, artifacts=(*result.artifacts,
                Resource('online-assessment.json', index, 'application/json', 'diagnostic')))
        finally:
            if handle is not None:
                await handle.aclose()
            release = getattr(self.services, 'release', None)
            if release is not None:
                for assessor in reversed(assessors):
                    await release(assessor)
