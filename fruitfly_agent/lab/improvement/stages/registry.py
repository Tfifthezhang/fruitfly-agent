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
class StageDefinition:
    name: str
    description: str
    controls: frozenset[str]
    required_inputs: tuple[str, ...] = ()
    allowance_fields: tuple[str, ...] = ()
    model_role: str | None = None
    effects: str = 'Offline material processing'


def stage_definitions():
    """One stage vocabulary for configuration, discovery and host binding."""
    return {
        item.name: item for item in (
            StageDefinition('eval', 'Execute a fixed prepared task collection', frozenset({'tasks'}),
                allowance_fields=('task_seconds',), effects='Task backends and model requests'),
            StageDefinition('import', 'Freeze retained permitted records',
                frozenset({'source', 'path', 'related_records', 'task_names', 'evidence_paths'})),
            StageDefinition('organize', 'Build an attributable reading guide', frozenset({'instruction'}),
                ('batches',), ('seconds', 'evidence_characters', 'evidence_responses'), 'organizer', 'Model requests'),
            StageDefinition('assess', 'Assess retained execution evidence', frozenset(),
                ('batches',), ('seconds', 'evidence_characters', 'evidence_responses'), 'assessor', 'Model requests'),
            StageDefinition('propose', 'Form and implement a candidate', frozenset({'direction', 'optimization'}),
                ('batches',), ('seconds', 'evidence_characters', 'evidence_responses'), 'editor', 'Model requests and candidate files'),
            StageDefinition('execute', 'Execute an explicitly selected harness', frozenset({'tasks', 'attempts', 'concurrency'}),
                ('harness',), ('task_seconds',), effects='Task backends and model requests'),
            StageDefinition('compare', 'Compare explicitly selected result batches', frozenset(),
                ('batches',), ('seconds', 'evidence_characters', 'evidence_responses'), 'assessor', 'Model requests'),
        )}


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
