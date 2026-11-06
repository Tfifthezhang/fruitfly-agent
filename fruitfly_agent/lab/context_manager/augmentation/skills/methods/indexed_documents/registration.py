"""One progressive Skill loader with independently editable retained content."""
from fruitfly_agent.core.context import ContextStage
from fruitfly_agent.core.mechanisms import MechanismDescriptor, MechanismContribution
from fruitfly_agent.lab.catalog.models import MechanismDefinition
from fruitfly_agent.lab.catalog.classification import CONTEXT, AUGMENTATION, SKILLS
from fruitfly_agent.lab.catalog.assembly import require_workspace_path
from fruitfly_agent.improvement.contracts.text import TEXT_TARGET_PREFIX
from fruitfly_agent.lab.context_manager.augmentation.skills.improvement import register
from fruitfly_agent.lab.context_manager.augmentation.skills.library import state_surface, capture_library
from fruitfly_agent.lab.context_manager.augmentation.skills.resources import capture_skills
from .config import parameters
from .algorithm import SkillCatalogTransformer
from .index import render_catalog


def snapshot(values, workspace):
    return capture_skills(require_workspace_path(workspace, values['root'], name='Skill root'), workspace).freeze()


def definition():
    return register(MechanismDefinition(MechanismDescriptor('skills', 'Skills',
        'Use installed coding procedures: descriptions guide selection and bodies load only when needed.',
        contributions=(MechanismContribution('online', 'context', 'augmentation'),),
        parameters=parameters(), default_enabled=True, install_order=30), install,
        feature_path=(CONTEXT, AUGMENTATION, SKILLS), requires_capabilities=frozenset({'resource-reader'}),
        implementation_id='indexed-documents-v1',
        implementation_path='fruitfly_agent/lab/context_manager/augmentation/skills/methods/indexed_documents/algorithm.py',
        documentation_path='fruitfly_agent/lab/context_manager/augmentation/skills/README.md',
        configuration_surfaces=(state_surface(),), configuration_snapshot=snapshot,
        default_resource=(__package__, 'defaults.yaml'),
        parameter_paths={'root': 'settings.root', 'usage': 'instructions.usage', 'max_chars': 'settings.max_chars'}))


def install(state, context, values):
    target = state.components[TEXT_TARGET_PREFIX + 'skill-library']
    captured = capture_library(target.list_entries(), context.workspace)
    catalog, directory = render_catalog(captured, context.resources)
    text = values['usage'] + '\n\n' + catalog if catalog else ''
    if captured.diagnostics:
        text += '\nSkill loading diagnostics:\n' + '\n'.join(captured.diagnostics[:8])
    state = state.with_component('skill-resources', captured)
    return state.with_context_stage(ContextStage('skills', 'augmentation',
        SkillCatalogTransformer(text, values['max_chars'], directory), order=30))
