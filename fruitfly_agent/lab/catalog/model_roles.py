"""Pure owner-declared model requirements and role-attributed Provider binding."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
import re
from typing import Any, Callable, Mapping
from uuid import uuid4

from fruitfly_agent.core.context.budget import forward_context_capabilities
from fruitfly_agent.core.model_stream import (AssistantMessageEventStream, StreamDone, TextDelta,
    ThinkingDelta, StreamActivity)
from fruitfly_agent.core.observation import FailureInfo, bind_observation, current_observation, start_operation


def always(values: Mapping[str, Any]) -> bool:
    return True


@dataclass(frozen=True)
class ModelRoleRequirement:
    parameter: str
    purpose: str
    required_when: Callable[[Mapping[str, Any]], bool] = always
    fallback_role: str | None = 'executor'
    lazy: bool = False

    def __post_init__(self) -> None:
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', self.parameter) or not self.purpose.strip():
            raise ValueError('model role needs a parameter and purpose')
        if not callable(self.required_when) or type(self.lazy) is not bool:
            raise ValueError('invalid model role requirement')
        if self.fallback_role is not None and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', self.fallback_role):
            raise ValueError('invalid model fallback role')


def role_alias(role: str, requirement: ModelRoleRequirement, values: Mapping[str, Any],
               roles: Mapping[str, str] | None = None) -> str | None:
    active = requirement.required_when(values)
    if type(active) is not bool:
        raise ValueError('model requirement condition must return boolean')
    if not active:
        return None
    alias = values.get(requirement.parameter, '')
    if not isinstance(alias, str):
        raise ValueError('model role alias must be a string: ' + role)
    if alias:
        return alias
    if roles is not None and roles.get(role):
        return roles[role]
    if requirement.fallback_role is not None:
        if roles is None:
            return None  # Offline alias discovery has no host executor selection.
        alias = roles.get(requirement.fallback_role)
        if alias:
            return alias
    raise ValueError('mechanism requires models.roles.' + role)


def required_profiles(requirements: Mapping[str, ModelRoleRequirement], values: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(sorted({alias for role, requirement in requirements.items()
        if (alias := role_alias(role, requirement, values)) is not None}))


class RoleProvider:
    """Attribute calls without retaining context tokens across generator yields."""
    def __init__(self, provider: Any, component_id: str, role: str) -> None:
        self.provider, self.component_id, self.role = provider, component_id, role
        forward_context_capabilities(self, provider)

    def __call__(self, view: Any, *, signal: Any = None) -> AssistantMessageEventStream:
        context = replace(current_observation(), component_id=self.component_id,
            model_role=self.role, request_id=uuid4().hex)
        async def events():
            stream = None
            saw_text = False
            activity = context.model_activity
            with bind_observation(context):
                observed = start_operation('model.auxiliary', origin='provider')
            if activity is not None:
                await activity(phase='model_started', component_id=self.component_id,
                    model_role=self.role, request_id=context.request_id, batch=0, total=0, text='')
            request_context = replace(context, parent_operation_id=observed.event.operation_id)
            try:
                with bind_observation(request_context):
                    stream = self.provider(view, signal=signal)
                while True:
                    try:
                        with bind_observation(request_context):
                            event = await anext(stream)
                    except StopAsyncIteration:
                        break
                    if activity is not None:
                        if isinstance(event, TextDelta):
                            saw_text = saw_text or bool(event.text)
                            await activity(phase='model_text', component_id=self.component_id,
                                model_role=self.role, request_id=context.request_id, batch=0, total=0, text=event.text)
                        elif isinstance(event, ThinkingDelta):
                            await activity(phase='model_thinking', component_id=self.component_id,
                                model_role=self.role, request_id=context.request_id, batch=0, total=0, text='')
                        elif isinstance(event, StreamActivity):
                            await activity(phase='model_status', component_id=self.component_id,
                                model_role=self.role, request_id=context.request_id, batch=0, total=0, text=event.phase)
                    yield event
                with bind_observation(request_context):
                    final = await stream.result()
                with bind_observation(request_context):
                    await stream.aclose()
                stream = None
                observed.finish()
                if activity is not None:
                    if not saw_text and final.text:
                        await activity(phase='model_text', component_id=self.component_id,
                            model_role=self.role, request_id=context.request_id, batch=0, total=0, text=final.text)
                    await activity(phase='model_finished', component_id=self.component_id,
                        model_role=self.role, request_id=context.request_id, batch=0, total=0, text='')
                yield StreamDone(final)
            except (asyncio.CancelledError, GeneratorExit):
                observed.state = 'cancelled'
                raise
            except Exception as exc:
                details = getattr(exc, 'details', None)
                recorded = details.get('failure') if isinstance(details, dict) else None
                observed.fail(FailureInfo.from_dict(recorded) if isinstance(recorded, dict) else
                    FailureInfo('provider', 'model.auxiliary', evidence_kind='exception_type', exception_type=type(exc).__name__))
                if activity is not None:
                    await activity(phase='model_failed', component_id=self.component_id,
                        model_role=self.role, request_id=context.request_id, batch=0, total=0, text=type(exc).__name__)
                raise
            finally:
                observed.finish()
                if stream is not None:
                    with bind_observation(context):
                        await stream.aclose()
        return AssistantMessageEventStream(events())
