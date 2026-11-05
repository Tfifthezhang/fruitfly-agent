"""Concrete resource ownership for one prepared runtime."""
from __future__ import annotations
from dataclasses import dataclass, field
from inspect import isawaitable
from typing import Any, Awaitable, Callable, Mapping
from fruitfly_agent.interactive.contracts.runtime import RuntimeSession, RuntimeAuthorization, RuntimeCleanupError
from fruitfly_agent.interactive.contracts.improvement import ImprovementService
from fruitfly_agent.interactive.contracts.candidates import CandidateActivationService, CandidateService
from fruitfly_agent.interactive.contracts.task_packs import TaskPackService
from fruitfly_agent.interactive.contracts.operations import OperationService
from fruitfly_agent.interactive.contracts.maintenance import MaintenanceService
from fruitfly_agent.interactive.contracts.retained_state import RetainedStateService
from fruitfly_agent.core.observation import ObservationContext, bind_observation, current_observation, operation, start_operation, FailureInfo


async def _call_optional(component: Any, method: str) -> Any:
    callback = getattr(component, method, None)
    if callback is None:
        return None
    result = callback()
    return await result if isawaitable(result) else result


@dataclass
class RuntimeHandle:
    """One assembled runtime plus deterministic component lifecycle."""

    session: RuntimeSession
    manifest: Mapping[str, Any]
    components: Mapping[str, Any] = field(default_factory=dict)
    close_callback: Callable[[], Awaitable[None] | None] | None = None
    improvement: ImprovementService | None = None
    candidate_activation: CandidateActivationService | None = None
    activate_callback: Callable[[], None] | None = None
    authorization: RuntimeAuthorization | None = None
    candidates: CandidateService | None = None
    task_packs: TaskPackService | None = None
    operations: OperationService | None = None
    observation_context: ObservationContext | None = None
    maintenance: MaintenanceService | None = None
    retained_state: RetainedStateService | None = None
    _closed: bool = field(default=False, init=False, repr=False)

    async def start(self) -> None:
        with bind_observation(self.observation_context or current_observation()):
            try:
                with operation('application.start', origin='application'):
                    seen: set[int] = set()
                    for component in self.components.values():
                        if id(component) in seen:
                            continue
                        seen.add(id(component))
                        await _call_optional(component, "start")
            except BaseException:
                await self.close()
                raise

    async def health(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, component in self.components.items():
            value = await _call_optional(component, "health")
            result[key] = "ready" if value is None else value
        return result

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        with bind_observation(self.observation_context or current_observation()):
            observed = start_operation('application.close', origin='application')
        with bind_observation(self.observation_context or current_observation()):
            errors: list[BaseException] = []
            if self.authorization is not None:
                try:
                    await self.authorization.close()
                except BaseException as exc:
                    errors.append(exc)
            seen: set[int] = set()
            for component in reversed(tuple(self.components.values())):
                if id(component) in seen:
                    continue
                seen.add(id(component))
                try:
                    await _call_optional(component, "close")
                except BaseException as exc:  # finish cleanup before surfacing failure
                    errors.append(exc)
            if errors:
                observed.fail(FailureInfo('application', 'application.close', 'cleanup.failed', 'runtime_rule'))
            observed.finish()
        if self.close_callback is not None:
            try:
                result = self.close_callback()
                if isawaitable(result):
                    await result
            except BaseException as exc:
                errors.append(exc)
        if errors:
            raise RuntimeCleanupError(f"runtime cleanup failed: {errors[0]}") from errors[0]


