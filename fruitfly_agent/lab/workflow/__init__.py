"""Bounded declarative execution workflows over the public Core callbacks."""
from dataclasses import replace
import json

from fruitfly_agent.core.data_model import UserMessage
from fruitfly_agent.core.mechanisms import MechanismDescriptor, MechanismContribution, MechanismEffects
from fruitfly_agent.lab.algorithms.targets import TargetBinding, TargetSnapshot, validate_text

WORKFLOW_TARGET = 'execution-workflow'
DEFAULT_WORKFLOW = '{"steps":["Solve the user task and return the final answer."]}'


def parse_workflow(text):
    validate_text(text)
    value = json.loads(text)
    if not isinstance(value, dict) or set(value) != {'steps'} or not isinstance(value['steps'], list):
        raise ValueError('workflow must contain only a steps array')
    steps = value['steps']
    if not 1 <= len(steps) <= 6 or any(not isinstance(s, str) or not s.strip() or len(s) > 2000 for s in steps):
        raise ValueError('workflow requires 1–6 nonempty steps of at most 2000 characters')
    for step in steps:
        validate_text(step)
        if '<!-- fruitfly:' in step:
            raise ValueError('workflow steps cannot contain projection delimiters')
    return tuple(steps)


def project_workflow(prompt, text):
    """Replace the owned first-step block in place, preserving context order."""
    steps = parse_workflow(text)
    start, end = '<!-- fruitfly:workflow:start -->', '<!-- fruitfly:workflow:end -->'
    block = f'{start}\n{steps[0]}\n{end}'
    if start in prompt:
        left = prompt.index(start)
        right = prompt.find(end, left)
        if right < 0 or start in prompt[right + len(end):]:
            raise ValueError('incomplete workflow projection')
        return prompt[:left] + block + prompt[right + len(end):]
    return prompt.rstrip() + '\n\n' + block


def apply_workflow(config, text):
    steps = parse_workflow(text)
    if config.get_follow_up_messages is not None:
        raise ValueError('execution workflow conflicts with an existing follow-up controller')
    if config.max_turns < len(steps):
        raise ValueError('workflow exceeds the configured turn limit')
    def follow_up(ctx):
        return [UserMessage(content=steps[ctx.turn_count])] if ctx.turn_count < len(steps) else []
    return replace(config, system_prompt=project_workflow(config.system_prompt, text),
                   get_follow_up_messages=follow_up)


class WorkflowTarget:
    label = 'Execution workflow'
    component_kind = 'execution-workflow'
    project_in_trials = True

    def __init__(self, text=DEFAULT_WORKFLOW):
        parse_workflow(text)
        self.text = text

    def snapshot(self):
        return TargetSnapshot(WORKFLOW_TARGET, self.text, TargetBinding('artifact', WORKFLOW_TARGET),
                              'execution-workflow-v1', 'H')

    def validate(self, text):
        parse_workflow(text)

    def prepare_trial(self, config, text):
        return replace(config, system_prompt=project_workflow(config.system_prompt, text))

    def prepare_execution(self, config, text):
        # Called after host isolation and Provider budgeting, so every stage is accounted.
        return apply_workflow(replace(config, max_turns=6), text)


def definition():
    from fruitfly_agent.lab.catalog.models import MechanismDefinition
    return MechanismDefinition(MechanismDescriptor(WORKFLOW_TARGET, 'Execution workflow',
        'Execute bounded model stages, including critique and revision, through normal Agent turns.',
        contributions=(MechanismContribution('online', 'workflow'),), install_order=70,
        effects=MechanismEffects(uses_provider=True, uses_network=True,
            lifecycle_hooks=('get_follow_up_messages',),
            cost_notice='Each workflow stage uses normal model calls and may incur cost.')),
        _install, implementation_id='declarative-workflow-v1', artifact_slots=frozenset({WORKFLOW_TARGET}),
        implementation_path='fruitfly_agent/lab/workflow/__init__.py',
        documentation_path='fruitfly_agent/lab/workflow/README.md')


def _install(state, context, parameters):
    from fruitfly_agent.lab.algorithms.targets import TEXT_TARGET_PREFIX
    text = DEFAULT_WORKFLOW
    reference = context.artifact_bindings.get(WORKFLOW_TARGET)
    if reference is not None:
        if context.artifact_reader is None:
            raise ValueError('workflow requires an artifact reader')
        text = context.artifact_reader(reference)
        state = state.with_data_artifact({'key': WORKFLOW_TARGET, 'id': reference,
            'media_type': 'text/plain; charset=utf-8', 'size_bytes': len(text.encode('utf-8'))})
    return replace(state, config=apply_workflow(state.config, text)).with_component(
        TEXT_TARGET_PREFIX + WORKFLOW_TARGET, WorkflowTarget(text))
