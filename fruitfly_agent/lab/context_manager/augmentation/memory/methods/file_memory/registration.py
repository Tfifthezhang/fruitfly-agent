"""One File memory H implementation with an independently bound S collection."""
from dataclasses import replace
from fruitfly_agent.core.mechanisms import MechanismDescriptor, MechanismContribution, MechanismEffects, ParameterDescriptor
from fruitfly_agent.lab.catalog.models import MechanismDefinition
from fruitfly_agent.lab.catalog.model_roles import ModelRoleRequirement
from fruitfly_agent.lab.catalog.classification import CONTEXT, AUGMENTATION, MEMORY
from fruitfly_agent.lab.catalog.adapters.parameters import editable_parameters
from fruitfly_agent.lab.catalog.adapters.collections import DocumentsTarget, collection_surface, parse_documents
from fruitfly_agent.runtime_spec.documents import parameter_default
from fruitfly_agent.improvement.contracts.versions import canonical_json
from .validation import validate_memories
from .models import MUTABLE
from .config import MaintenanceConfig
from .maintenance import ThresholdMaintenance
from .algorithm import install_reading


def state_surface():
    def normalize(parameters):
        if (not isinstance(parameters, dict) or set(parameters) != {'content'}
                or not isinstance(parameters['content'], dict) or set(parameters['content']) != {'documents'}):
            raise ValueError('memory state requires content.documents')
        entries = validate_memories(parse_documents(parameters['content']['documents']))
        return {'content': {'documents': canonical_json(entries)}}
    def factory(state, context, parameters):
        return DocumentsTarget(state_surface(), parameters['content'], label='Retained memories', kind='memory',
            validate_documents=validate_memories, mutable=MUTABLE)
    return collection_surface('memory-library', normalize=normalize,
        default_resource=(__package__, 'state.yaml'), factory=factory)


def definition():
    def default(path):
        return parameter_default(__package__, 'defaults.yaml', path)
    params = (
        ParameterDescriptor('root', 'string', 'Memory namespace', 'Protected workspace-relative resource namespace.', default('settings.root')),
        ParameterDescriptor('usage', 'string', 'Reading instructions', 'When and why retained notes should be read.', default('instructions.reading')),
        ParameterDescriptor('max_chars', 'integer', 'Directory characters', 'Bound directory metadata; bodies load on demand.', default('settings.max_chars'), minimum=256, maximum=16000),
        ParameterDescriptor('maintenance_enabled', 'boolean', 'Automatic maintenance', 'Prepare memory updates after user-input thresholds.', default('settings.maintenance_enabled')),
        ParameterDescriptor('extraction', 'string', 'Extraction instructions', 'Extract supported durable notes from attributed user input.', default('instructions.extraction')),
        ParameterDescriptor('consolidation', 'string', 'Consolidation instructions', 'Organize retained notes without losing unrelated entries or provenance.', default('instructions.consolidation')),
        *(ParameterDescriptor(name, 'integer', name.replace('_', ' ').capitalize(),
            'Maintenance trigger or invocation bound; user-input counters accumulate across sessions.',
            default('settings.' + name), minimum=1, maximum=1000000) for name in MaintenanceConfig.__dataclass_fields__),
        ParameterDescriptor('model_profile', 'string', 'Maintenance model', 'Lazy host-bound model alias; inherits executor.', ''),
    )
    paths = {p.name: 'settings.' + p.name for p in params}
    paths.update({'usage': 'instructions.reading', 'extraction': 'instructions.extraction', 'consolidation': 'instructions.consolidation'})
    value = MechanismDefinition(MechanismDescriptor('file-memory', 'File memory',
        'Keep attributed cross-session notes; read bodies on demand and maintain them after simple input thresholds.',
        contributions=(MechanismContribution('online', 'context', 'augmentation'),), default_enabled=True,
        install_order=40, parameters=params,
        effects=MechanismEffects(uses_provider=True, uses_network=True, writes_files=True,
            cost_notice='Threshold maintenance may call the selected model; directory loading makes no model requests.')),
        install, feature_path=(CONTEXT, AUGMENTATION, MEMORY),
        requires_capabilities=frozenset({'resource-reader'}),
        selection_group='memory', selection_group_label='Memory',
        default_resource=(__package__, 'defaults.yaml'), parameter_paths=paths,
        configuration_surfaces=(state_surface(),),
        input_parameters=('maintenance_enabled', 'extract_after_user_chars', 'consolidate_after_user_turns'),
        model_role_parameters={'memory_maintenance': ModelRoleRequirement('model_profile',
            'Extract and consolidate retained notes.', lazy=True, required_when=lambda p: p['maintenance_enabled'])},
        implementation_path='fruitfly_agent/lab/context_manager/augmentation/memory/methods/file_memory/algorithm.py',
        documentation_path='fruitfly_agent/lab/context_manager/augmentation/memory/methods/file_memory/README.md')
    return editable_parameters(value, {p.name for p in params} - {'root', 'model_profile'},
        required_capabilities={'memory-learning'})


def install(state, context, values):
    state = install_reading(state, context, values)
    def worker_for(parameters):
        role_context = replace(context, model_parameters=parameters)
        return ThresholdMaintenance(MaintenanceConfig(**{k: parameters[k] for k in MaintenanceConfig.__dataclass_fields__}),
            parameters['extraction'], parameters['consolidation'], lambda: role_context.provider_for_role('memory_maintenance'))
    state = state.with_execution_resource('memory-learning', worker_for)
    if values['maintenance_enabled']:
        worker = worker_for(values)
        state = state.with_component('maintenance-workers', (*state.components.get('maintenance-workers', ()), worker))
    return state
