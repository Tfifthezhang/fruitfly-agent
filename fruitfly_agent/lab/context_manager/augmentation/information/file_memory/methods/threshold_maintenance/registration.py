"""Declare maintenance H policy, I instructions and lazy model dependency."""
from dataclasses import replace
from fruitfly_agent.core.mechanisms import MechanismDescriptor, MechanismContribution, MechanismEffects, ParameterDescriptor
from fruitfly_agent.lab.catalog.models import MechanismDefinition
from fruitfly_agent.lab.catalog.model_roles import ModelRoleRequirement
from fruitfly_agent.lab.improvement.components.parameters import editable_parameters
from fruitfly_agent.runtime_spec.documents import parameter_default
from .algorithm import ThresholdMaintenance
from .config import MaintenanceConfig


def definitions():
    result = []
    for name, resource in (('memory-extractor', 'extraction.yaml'), ('memory-consolidator', 'consolidation.yaml')):
        def install(state, context, values, key=name):
            return state.with_component(key, values['prompt'])
        definition = MechanismDefinition(MechanismDescriptor(name, name.replace('-', ' ').title(),
            'Generate attributed S candidates without publication authority: ' + name + '.',
            contributions=(MechanismContribution('improvement', 'workflow'),), install_order=26,
            parameters=(ParameterDescriptor('prompt', 'string', 'Editing instructions',
                'Instructions used in actual memory candidate generation.', parameter_default(__package__, resource, 'instructions.prompt')),)),
            install, configuration_role='I', default_resource=(__package__, resource),
            parameter_paths={'prompt': 'instructions.prompt'},
            implementation_path='fruitfly_agent/lab/context_manager/augmentation/information/file_memory/methods/threshold_maintenance/algorithm.py',
            documentation_path='fruitfly_agent/lab/context_manager/augmentation/information/file_memory/methods/threshold_maintenance/README.md')
        result.append(editor_definition(editable_parameters(definition, {'prompt'})))
    params = tuple(ParameterDescriptor(name, 'integer', name.replace('_', ' ').title(),
        'Threshold or invocation bound used by cross-session memory maintenance.', value, minimum=1, maximum=1000000)
        for name, value in vars(MaintenanceConfig()).items())
    policy = MechanismDefinition(MechanismDescriptor('memory-maintenance', 'Threshold memory maintenance',
        'Prepare memory candidates only after input increments reach configured thresholds. Model calls may incur cost.',
        contributions=(MechanismContribution('improvement', 'workflow'),), install_order=45,
        requires=frozenset({'memory-library', 'memory-extractor', 'memory-consolidator'}),
        effects=MechanismEffects(uses_provider=True, uses_network=True, writes_files=True,
            cost_notice='Idle memory extraction and consolidation can make paid model requests.'),
        parameters=(*params, ParameterDescriptor('model_profile', 'string', 'Memory editor model', 'Host-bound auxiliary model alias.', ''))),
        install_maintenance, default_resource=(__package__, 'defaults.yaml'),
        parameter_paths={**{name: 'settings.' + name for name in vars(MaintenanceConfig())}, 'model_profile': 'settings.model_profile'},
        model_role_parameters={'memory_maintenance': ModelRoleRequirement('model_profile', 'Extract and consolidate cross-session memory.', lazy=True)},
        implementation_path='fruitfly_agent/lab/context_manager/augmentation/information/file_memory/methods/threshold_maintenance/algorithm.py',
        documentation_path='fruitfly_agent/lab/context_manager/augmentation/information/file_memory/methods/threshold_maintenance/README.md')
    return (*result, editable_parameters(policy, set(vars(MaintenanceConfig()))))


def install_maintenance(state, context, values):
    worker = ThresholdMaintenance(MaintenanceConfig(**{k: v for k, v in values.items() if k != 'model_profile'}),
        state.components['memory-extractor'], state.components['memory-consolidator'],
        lambda: context.provider_for_role('memory_maintenance'))
    return state.with_component('maintenance-workers', (*state.components.get('maintenance-workers', ()), worker))


def editor_definition(definition):
    original = definition.install
    original_specs = definition.component_specs
    def install(state, context, values):
        state = original(state, context, values)
        from fruitfly_agent.lab.improvement.targets.text import TEXT_TARGET_PREFIX
        target = state.components[TEXT_TARGET_PREFIX + definition.descriptor.mechanism_id]
        target.optimization = replace(target.optimization, required_capabilities=
            target.optimization.required_capabilities | frozenset({'memory-maintenance-comparison'}))
        return state
    def specs(values, enabled):
        return tuple(replace(spec, required_capabilities=spec.required_capabilities |
            frozenset({'memory-maintenance-comparison'})) for spec in original_specs(values, enabled))
    return replace(definition, install=install, component_specs=specs)
