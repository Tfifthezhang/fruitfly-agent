"""A compact reusable Skill body, independent of catalog guidance and source files."""
from fruitfly_agent.core.mechanisms import MechanismDescriptor, MechanismContribution, ParameterDescriptor
from fruitfly_agent.lab.algorithms.retained import install_retained, configuration_edit
from fruitfly_agent.lab.algorithms.snapshots import WorkspaceTextSnapshots
from fruitfly_agent.lab.algorithms.targets import STATE_SNAPSHOTS_COMPONENT
from .catalog import load_skill_document

SKILL_DOCUMENT = 'skill-document'


def definition():
    from fruitfly_agent.lab.catalog.models import MechanismDefinition
    from fruitfly_agent.lab.catalog.components import ComponentSpec
    return MechanismDefinition(MechanismDescriptor(SKILL_DOCUMENT, 'Reusable skill document',
        'Retain a compact procedural Skill body; improve it explicitly through Improvement.',
        contributions=(MechanismContribution('online', 'context', 'augmentation'),),
        parameters=(ParameterDescriptor('initial_text', 'string', 'Initial skill text',
            'Starting procedural document. Adopted artifacts take precedence; source Skill files are unchanged.',
            '# Reusable skill\nNo validated procedures recorded yet.'),
            ParameterDescriptor('source_path', 'string', 'Source Skill file',
                'Optional workspace-relative SKILL.md. Its body seeds the target; relative references keep its directory.', ''),
            ParameterDescriptor('max_chars', 'integer', 'Document characters',
                'Maximum complete Skill body projected into context.', 16000, minimum=128, maximum=30000)),
        install_order=32), _install, implementation_id='retained-skill-v1',
        artifact_slots=frozenset({SKILL_DOCUMENT}), configuration_role='S',
        configuration_edit=configuration_edit,
        configuration_snapshot=_snapshot,
        component_specs=lambda parameters, enabled: (ComponentSpec(SKILL_DOCUMENT, 'S', 'retained-document', 'skill-document-v1'),) if enabled else (),
        implementation_path='fruitfly_agent/lab/context_manager/augmentation/skills/document.py',
        documentation_path='fruitfly_agent/lab/context_manager/augmentation/skills/README.md',
        input_parameters=('initial_text', 'source_path'))


def _snapshot(parameters, workspace):
    from pathlib import Path
    from fruitfly_agent.improvement.contracts.versions import StateSnapshot
    if not parameters['source_path']:
        return StateSnapshot()
    path = Path(parameters['source_path'])
    if path.is_absolute() or not (workspace / path).resolve().is_relative_to(workspace):
        raise ValueError('source Skill must be workspace-relative')
    load_skill_document(workspace / path)
    return WorkspaceTextSnapshots((workspace / path).parent, workspace).freeze()


def _install(state, context, parameters):
    from pathlib import Path
    initial, label, reference_directory = parameters['initial_text'], 'Skill document', ''
    if parameters['source_path']:
        path = context.workspace / parameters['source_path']
        if Path(parameters['source_path']).is_absolute() or not path.resolve().is_relative_to(context.workspace):
            raise ValueError('source Skill must be workspace-relative')
        skill = load_skill_document(path)
        initial, label, reference_directory = skill.content, 'Skill: ' + skill.name, str(path.parent.resolve())
        state = state.with_component(STATE_SNAPSHOTS_COMPONENT,
            (*state.components.get(STATE_SNAPSHOTS_COMPONENT, ()), WorkspaceTextSnapshots(path.parent, context.workspace)))
    return install_retained(state, context, key=SKILL_DOCUMENT, label=label,
        schema='skill-document-v1', initial=initial, max_chars=parameters['max_chars'],
        reference_directory=reference_directory)
