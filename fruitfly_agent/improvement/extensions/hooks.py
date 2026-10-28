"""Deterministic job-local observers and narrowly scoped active extensions."""
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable
from ..contracts.tasks import Resource
from ..contracts.lifecycle import HOOK_NAMES, ContextContribution, LifecycleEvent
from ..contracts.validation import identifier
from ..contracts.failures import StageFailure
from ..workflow.operations import run_stage


@dataclass(frozen=True)
class Handler:
    name: str
    callback: Callable[[LifecycleEvent], Any]
    active: bool
    required: bool
    priority: int
    identity: str


class HookRegistry:
    def __init__(self):
        self.handlers = []

    def register(self, name, callback, *, active=False, required=False, priority=100, identity='observer'):
        identifier(identity)
        if name not in HOOK_NAMES or not callable(callback):
            raise ValueError('hooks need a registered event and callable')
        if active and name != 'before_proposal':
            raise ValueError('only before_proposal accepts context contributions')
        if type(priority) is not int or type(active) is not bool or type(required) is not bool:
            raise ValueError('hook metadata must be explicit')
        self.handlers.append(Handler(name, callback, active, required, priority, identity))

    def on(self, name, callback, **options):
        self.register(name, callback, **options)

    async def dispatch(self, event, services):
        resources: list[Resource] = []
        handlers = sorted((h for h in self.handlers if h.name == event.name), key=lambda h: (not h.active, h.priority))
        for handler in handlers:
            def validate(value):
                if handler.active:
                    if value is not None and not isinstance(value, ContextContribution):
                        raise TypeError('active hooks return ContextContribution or None')
                elif value is not None:
                    raise TypeError('observers cannot return control results')
                if isinstance(value, ContextContribution):
                    ContextContribution(tuple(resources) + value.resources)
            try:
                result = await run_stage(services, 'hook', lambda: handler.callback(deepcopy(event)), validator=validate)
            except StageFailure as exc:
                services.record('hook-failed', hook=handler.identity, name=event.name,
                    required=handler.required, code=exc.failure.code)
                if handler.required:
                    raise
                continue
            if isinstance(result, ContextContribution):
                resources.extend(result.resources)
        return ContextContribution(tuple(resources))
