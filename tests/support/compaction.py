"""Mounted history and deterministic evidence for reduction checks."""
from fruitfly_agent.core.data_model import ContextItem, ContextSnapshot, UserMessage, AssistantMessage, ToolCallBlock, ToolResultMessage, TextBlock
from fruitfly_agent.lab.context_manager.resources import SessionHistory
from fruitfly_agent.lab.context_manager.resources.views import history_view
from fruitfly_agent.lab.tools.resources import ResourceRegistry


def mounted_history(*, root=None, session=None):
    history = SessionHistory(root, session=session)
    registry = ResourceRegistry()
    history.resource_prefix = registry.mount('compaction', lambda path: history_view(history, path))
    return history, registry


def source_messages(*, tools=False):
    messages = [UserMessage('Build the report; preserve verified numbers and check errors.')]
    for index in range(8):
        if tools:
            call = 'read-' + str(index)
            messages.extend((AssistantMessage([ToolCallBlock(call, 'read', {'path':str(index)})]),
                ToolResultMessage(call, [TextBlock('Original result ' + str(index) + ': ' + 'evidence ' * 450)], is_error=index==2)))
        else:
            messages.extend((AssistantMessage([TextBlock('Observed evidence ' + str(index) + ': ' + 'value ' * 450)]),
                             UserMessage('Correction ' + str(index) + ': keep the result attributed.')))
    messages.append(UserMessage('Now finish the report and verify the result.'))
    return messages


def snapshot(messages, **overrides):
    values = dict(canonical_items=tuple(ContextItem('source-' + str(i), m) for i,m in enumerate(messages)),
        messages=tuple(messages), system_prompt='Task execution.', tools=(), context_window=5000,
        model='offline', max_tokens=128, trigger='budget')
    values.update(overrides)
    return ContextSnapshot(**values)


def structured_summary(marker='Verified facts retained.'):
    from fruitfly_agent.lab.context_manager.reduction.methods.layered_compaction.prompts import SECTIONS
    return '\n\n'.join('## ' + heading + '\n' + marker for heading in SECTIONS)
