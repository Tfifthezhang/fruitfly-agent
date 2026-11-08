"""Bind independent stage handlers to a narrow injected context."""
from dataclasses import dataclass
from functools import partial
from typing import Any, Callable
from .organize import organize
from .assess import assess
from .propose import propose
from .execute import execute
from .compare import compare
from fruitfly_agent.improvement.contracts.stages import StageInputs


@dataclass(frozen=True)
class StageContext:
    plan: Any
    proposal: Any
    organizer: Any
    assessor: Any
    executor: Any
    put: Callable
    read: Callable
    read_batch: Callable
    input_batch: Callable
    create_services: Callable


def builtin_stage_handlers(context):
    return {(name, 'research-' + name + '-v1'): partial(invoke_named, handler, context)
        for name, handler in (('organize', organize), ('assess', assess),
            ('propose', propose), ('execute', execute), ('compare', compare))}


async def invoke_named(handler, context, spec):
    inputs = StageInputs.from_dict(spec.parameters.get('named_inputs', {})).validate_for(spec.kind)
    granted = (() if inputs.harness is None else (inputs.harness,)) + inputs.batches + inputs.evidence + inputs.assessments + inputs.context
    if set(granted) != set(spec.inputs):
        raise ValueError('named stage inputs differ from the declared artifact grant')
    return await handler(context, spec, inputs)
