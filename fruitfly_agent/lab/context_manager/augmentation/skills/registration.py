"""Shared assembly for discovered Skill metadata and editable usage policy."""
from fruitfly_agent.core.context import ContextStage
from fruitfly_agent.core.mechanisms import MechanismDescriptor, MechanismContribution
from fruitfly_agent.improvement.contracts.versions import STATE_SNAPSHOTS_COMPONENT
from fruitfly_agent.lab.catalog.models import MechanismDefinition
from fruitfly_agent.lab.catalog.assembly import require_workspace_path
from .configuration import parameters
from .improvement import register
from .catalog import render_skills_xml
from .resources import capture_skills
from .adapter import SkillCatalogTransformer


def snapshot(values, workspace):
    return capture_skills(require_workspace_path(workspace, values['root'], name='Skill root'), workspace).freeze()


def definition():
    return register(MechanismDefinition(MechanismDescriptor('skill-catalog', 'Skill catalog',
        'Discover Skill metadata and describe how to use it.',
        contributions=(MechanismContribution('online', 'context', 'augmentation'),),
        parameters=parameters(), default_enabled=True, install_order=30), install,
        implementation_id='skill-catalog',
        implementation_path='fruitfly_agent/lab/context_manager/augmentation/skills/adapter.py',
        documentation_path='fruitfly_agent/lab/context_manager/augmentation/skills/README.md',
        input_parameters=('root',), configuration_snapshot=snapshot, default_resource=(__package__, 'skill-catalog.yaml'),
        parameter_paths={'root':'settings.root', 'usage':'instructions.usage', 'max_chars':'settings.max_chars'}))


def install(state, context, values):
    root = require_workspace_path(context.workspace, values['root'], name='Skill root')
    captured = capture_skills(root, context.workspace)
    state = state.with_component(STATE_SNAPSHOTS_COMPONENT,
        (*state.components.get(STATE_SNAPSHOTS_COMPONENT, ()), captured))
    locations = captured.mount(context.resources)
    catalog = render_skills_xml(list(captured.skills), locations=locations)
    text = values['usage'] + '\n\n' + catalog if catalog else ''
    if captured.diagnostics:
        text += '\nSkill loading diagnostics:\n' + '\n'.join(captured.diagnostics[:8])
        if context.session is not None:
            context.session.append('meta', {'kind': 'contextSourceDiagnostics',
                'component': 'skill-catalog', 'diagnostics': list(captured.diagnostics)})
    state = state.with_component('skill-catalog-resources', captured)
    return state.with_context_stage(ContextStage('skill-catalog', 'augmentation',
        SkillCatalogTransformer(text, values['max_chars']), order=30))
