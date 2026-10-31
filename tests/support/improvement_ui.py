"""Renderer-neutral workflow declarations for offline menu checks."""
from fruitfly_agent.interactive.contracts.improvement import (
    WorkflowConfiguration, WorkflowComponentView, WorkflowChoice, ImprovementParameterView)


def configuration():
    return WorkflowConfiguration(
        (WorkflowComponentView('base_prompt', 'Base prompt', 'system-prompt', 'H'),
         WorkflowComponentView('memory', 'Memory', 'memory', 'S'),
         WorkflowComponentView('editor', 'Editor', 'instructions', 'I', False, 'Comparison runner required')),
        (WorkflowChoice('rule', 'Rule generator'), WorkflowChoice('agent', 'Agent editor')),
        (WorkflowChoice('parallel', 'Parallel'), WorkflowChoice('sequential', 'Sequential')),
        (WorkflowChoice('behavior', 'Execution evidence'),),
        (WorkflowChoice('task', 'Current task'), WorkflowChoice('persistent', 'Persistent')),
        (ImprovementParameterView('width', 'Width', 'integer', 1, 1, 10, 'search', 'Exploration width'),
         ImprovementParameterView('depth', 'Depth', 'integer', 1, 1, 10, 'search', 'Refinement depth'),
         ImprovementParameterView('editor_seconds', 'Editor time', 'number', 1200, 0, None, 'timing', 'Independent editor invocation time')),
        (WorkflowChoice('', 'Current task and input files'), WorkflowChoice('pack', 'Saved package')))

from types import SimpleNamespace
from unittest.mock import Mock, AsyncMock
from fruitfly_agent.interactive.contracts.improvement import ImprovementPreview
from fruitfly_agent.interactive.terminal.features.improvement.workflow_panel import WorkflowPanel

def panel(choices, *, text=(), confirmed=False):
    selection, values = iter(choices), iter(text)
    frames, notices = [], []
    def choose(title, rows, **options):
        frames.append((title, rows, options))
        return next(selection)
    async def read(prompt):
        return next(values)
    client = SimpleNamespace(workflow_preview=Mock(return_value=ImprovementPreview('rule', 'Rule', 'Costs', preview_token='token')))
    panel = WorkflowPanel(client=client, configuration=configuration(), choose=choose, read=read,
        confirm=Mock(return_value=confirmed), report=notices.append, execute=AsyncMock(return_value=False), history=AsyncMock())
    return panel, client, frames, notices

