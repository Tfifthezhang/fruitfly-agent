"""One boundary around invocation, awaiting and returned-value validation."""
import asyncio
import inspect
from dataclasses import asdict
from ..contracts.assessment import AssessmentUnavailable
from ..contracts.failures import Failure, IntegrityError, StageFailure
from .budget import AllocationExhausted


async def run_stage(services, stage, operation, *, validator=None, bounded=True):
    """Accept a deferred callable so synchronous plugin failures are also isolated."""
    try:
        services.record('stage-started', stage=stage)
    except BaseException:
        if inspect.iscoroutine(operation):
            operation.close()
        raise
    retained = len(services.interrupted_records)
    async def invoke():
        services.check()
        value = operation() if callable(operation) else operation
        if inspect.isawaitable(value):
            value = await value
        if validator is not None:
            checked = validator(value)
            if inspect.isawaitable(checked):
                await checked
        services.check()
        return value
    try:
        value = await services.operation(invoke()) if bounded else await invoke()
    except (asyncio.CancelledError, AllocationExhausted, AssessmentUnavailable, IntegrityError):
        raise
    except Exception as exc:
        services.budget.check_root()
        failure = exc.failure if isinstance(exc, StageFailure) else Failure(
            stage, 'timeout' if isinstance(exc, TimeoutError) else 'unavailable', type(exc).__name__)
        services.record('stage-failed', **asdict(failure))
        if not failure.recoverable:
            raise IntegrityError('nonrecoverable stage failure: ' + failure.stage) from exc
        records = services.interrupted_records[retained:]
        receipt = exc.record if isinstance(exc, StageFailure) else records[0] if len(records) == 1 else None
        raise StageFailure(failure, receipt) from exc
    services.record('stage-finished', stage=stage)
    return value


def require_type(value, expected, *, optional=False):
    if value is None and optional:
        return
    if not isinstance(value, expected):
        raise TypeError('stage returned an invalid result type')


def validate_assessment_result(value, original):
    from dataclasses import replace
    from ..contracts.execution import ExecutionRecord
    from ..contracts.live import Assessment
    if not isinstance(value, tuple) or len(value) != 2:
        raise TypeError('assessment must return an execution and assessment tuple')
    record, assessments = value
    require_type(record, ExecutionRecord)
    if not isinstance(assessments, tuple) or any(not isinstance(a, Assessment) for a in assessments):
        raise TypeError('assessment values must be immutable assessment records')
    if replace(record, artifacts=original.artifacts) != original or not set(original.artifacts) <= set(record.artifacts):
        raise IntegrityError('assessment changed immutable execution evidence')
    if any(a.position.execution_id != original.run_id or a.position.version_id != original.harness_id
           or a.visibility != 'development' for a in assessments):
        raise IntegrityError('assessment differs from granted execution identity or visibility')


def diagnostic_reference(record, artifacts):
    if record.status == 'completed':
        return True
    if artifacts is None:
        return False
    from ..execution.facts import read_facts
    facts = read_facts(record, artifacts)
    return facts is not None and facts.diagnosable
