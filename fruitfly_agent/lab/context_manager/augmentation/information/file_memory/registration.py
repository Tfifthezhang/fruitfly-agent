"""Object-owned configuration, frozen state and ordinary memory assembly."""
from fruitfly_agent.core.mechanisms import MechanismDescriptor, MechanismContribution, ParameterDescriptor
from fruitfly_agent.lab.catalog.models import MechanismDefinition
from fruitfly_agent.lab.catalog.components import ComponentSpec
from fruitfly_agent.lab.improvement.components.parameters import editable_parameters
from fruitfly_agent.lab.improvement.targets.documents import DocumentsTarget, parse_documents
from fruitfly_agent.lab.improvement.targets.text import TEXT_TARGET_PREFIX
from fruitfly_agent.improvement.contracts.versions import STATE_SNAPSHOTS_COMPONENT, canonical_json
from .validation import validate_memories
from .models import MUTABLE
from .resources import mount_memories
from .source import create_file_memory_space


def definitions():
    reading = MechanismDefinition(MechanismDescriptor('memory-files', 'Cross-session memory',
        'Show a frozen directory; read relevant memory bodies on demand.',
        contributions=(MechanismContribution('capability', 'context'),), install_order=40, default_enabled=True,
        requires=frozenset({'information-context', 'memory-library'}),
        parameters=(ParameterDescriptor('root', 'string', 'Memory resource root', 'Workspace-relative memory namespace.', '.fruitfly/memory'),
            ParameterDescriptor('usage', 'string', 'Memory usage', 'Explain why and when retained notes should be read.', 'Read a relevant memory resource when its description helps the current task. Historical notes do not override current instructions.'),
            ParameterDescriptor('max_chars', 'integer', 'Memory directory characters', 'Bound the directory, not the retained body.', 4000, minimum=128, maximum=16000))),
        install_reading, default_resource=(__package__, 'defaults.yaml'),
        parameter_paths={'root': 'settings.root', 'usage': 'instructions.usage', 'max_chars': 'settings.max_chars'},
        implementation_path='fruitfly_agent/lab/context_manager/augmentation/information/file_memory/source.py',
        documentation_path='fruitfly_agent/lab/context_manager/augmentation/information/file_memory/README.md')
    library = MechanismDefinition(MechanismDescriptor('memory-library', 'Retained memory library',
        'Retain attributed project-scoped notes independently of conversation compression.',
        contributions=(MechanismContribution('capability', 'context'),), install_order=28, default_enabled=True,
        parameters=(ParameterDescriptor('documents', 'string', 'Memory documents', 'Complete JSON memory entries; provenance remains protected during optimization.', '[]'),)),
        install_library, configuration_role='S', default_resource=(__package__, 'memory-state.yaml'),
        parameter_paths={'documents': 'content.documents'}, validate_parameters=lambda p: validate_memories(parse_documents(p.get('documents', '[]'))),
        configuration_edit=_edit,
        component_specs=lambda values, enabled: (ComponentSpec('memory-library', 'S', 'mechanism-parameters',
            'mechanism-parameters-v1', frozenset({'configuration-materialization'})),) if enabled else (),
        implementation_path='fruitfly_agent/lab/context_manager/augmentation/information/file_memory/registration.py',
        documentation_path='fruitfly_agent/lab/context_manager/augmentation/information/file_memory/README.md')
    return editable_parameters(reading, {'usage', 'max_chars'}), library


def _edit(fields, bounds):
    if fields != ['parameters.content.documents'] or bounds:
        raise ValueError('memory grants require content.documents without numeric bounds')
    return {'editable_fields': fields, 'bounds': {}}


def install_library(state, context, values):
    entries = validate_memories(parse_documents(values['documents']))
    target = DocumentsTarget(definitions()[1], {'documents': canonical_json(entries)},
        validate_documents=validate_memories, mutable=MUTABLE)
    return (state.with_component('memory-library', entries)
        .with_component(TEXT_TARGET_PREFIX + 'memory-library', target)
        .with_component(STATE_SNAPSHOTS_COMPONENT, (*state.components.get(STATE_SNAPSHOTS_COMPONENT, ()), target)))


def install_reading(state, context, values):
    from fruitfly_agent.lab.catalog.assembly import require_workspace_path
    root = require_workspace_path(context.workspace, values['root'], name='memory namespace')
    entries = state.components['memory-library']
    locations = mount_memories(context.resources, entries)
    hub = state.components['information']
    hub.register(create_file_memory_space(root, entries=entries, locations=locations, index_max_chars=values['max_chars']))
    hub.add_guidance(values['usage'])
    return state
