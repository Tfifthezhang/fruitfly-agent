"""Concrete resource ownership for one prepared runtime."""
from __future__ import annotations
from dataclasses import dataclass, field
from inspect import isawaitable
from typing import Any, Awaitable, Callable, Mapping
from fruitfly_agent.interactive.contracts.runtime import RuntimeSession, RuntimeAuthorization
from fruitfly_agent.interactive.contracts.improvement import ImprovementService
from fruitfly_agent.interactive.contracts.candidates import CandidateActivationService, CandidateService
from fruitfly_agent.interactive.contracts.task_packs import TaskPackService


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
    _closed: bool = field(default=False, init=False, repr=False)

    async def start(self) -> None:
        seen: set[int] = set()
        try:
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
        if self.authorization is not None:
            await self.authorization.close()
        errors: list[BaseException] = []
        seen: set[int] = set()
        for component in reversed(tuple(self.components.values())):
            if id(component) in seen:
                continue
            seen.add(id(component))
            try:
                await _call_optional(component, "close")
            except BaseException as exc:  # finish cleanup before surfacing failure
                errors.append(exc)
        if self.close_callback is not None:
            try:
                result = self.close_callback()
                if isawaitable(result):
                    await result
            except BaseException as exc:
                errors.append(exc)
        if errors:
            raise RuntimeError(f"runtime cleanup failed: {errors[0]}") from errors[0]


