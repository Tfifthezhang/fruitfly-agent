"""One generic workflow configuration; stage implementations are injected ports."""
from dataclasses import replace
from fruitfly_agent.lab.catalog.classification import IMPROVEMENT

from fruitfly_agent.core.mechanisms import MechanismDescriptor, MechanismContribution, MechanismEffects, ParameterDescriptor as P
from fruitfly_agent.improvement.contracts.text import TEXT_TARGET_PREFIX
from .editor.instructions import EditorInstructions, EditorInstructionTarget
from fruitfly_agent.lab.catalog.model_roles import ModelRoleRequirement, RoleProvider


SETTINGS = 'component-improvement-settings'
EDITOR_CONFIG = 'component-improvement-editor-config'
ORGANIZER_CONFIG = 'component-improvement-organizer-config'
ASSESSOR_CONFIG = 'component-improvement-assessor-config'
EDITOR_INSTRUCTIONS = 'component-improvement-editor-instructions'
SYSTEM_SETTINGS = 'system-component-settings'


def definition():
    from fruitfly_agent.lab.catalog.models import MechanismDefinition
    from fruitfly_agent.lab.catalog.components import ComponentSpec
    from .system_configuration import configuration_surfaces, validate_component_options
    return MechanismDefinition(MechanismDescriptor('component-improvement', 'Component improvement',
        'Configure editor and evaluator models without starting improvement.',
        contributions=(MechanismContribution('improvement', 'context'),),
        default_enabled=False,
        parameters=(P('editor_profile', 'string', 'Editor model', 'Model catalog profile; empty reuses the active model.', ''),
            P('organizer_profile', 'string', 'Organizer model', 'Model catalog profile; empty reuses executor.', ''),
            P('assessor_profile', 'string', 'Assessment model', 'Model catalog profile; empty reuses the active model.', '')),
        install_order=76, effects=MechanismEffects(uses_provider=True, uses_network=True, writes_files=True,
            cost_notice="Explicit improvement runs call models and execute tasks; registration makes no requests.")),
        _install, visible=False, configurable=False, feature_path=(IMPROVEMENT,), implementation_id='component-workflow-v1', configuration_role='I',
        configuration_surfaces=configuration_surfaces(),
        model_role_parameters={'organizer': ModelRoleRequirement('organizer_profile', 'Organize experiment records for reading.', fallback_role='executor', lazy=True), 'editor': ModelRoleRequirement('editor_profile', 'Generate candidates.', fallback_role='executor', lazy=True),
            'assessor': ModelRoleRequirement('assessor_profile', 'Assess candidate evidence.', fallback_role='executor', lazy=True)},
        component_validator=validate_component_options,
        artifact_slots=frozenset({'improvement-editor', 'improvement-evaluator', 'improvement-organizer'}), prepare_targets=_prepare_targets,
        implementation_path='fruitfly_agent/lab/improvement/registration.py',
        documentation_path='fruitfly_agent/lab/improvement/README.md')


def _install(state, context, parameters):
    return (state.with_component(SETTINGS, dict(parameters))
        .with_component(ORGANIZER_CONFIG, _lazy_role_config(state.config, context, 'organizer'))
        .with_component(EDITOR_CONFIG, _lazy_role_config(state.config, context, 'editor'))
        .with_component(ASSESSOR_CONFIG, _lazy_role_config(state.config, context, 'assessor')))


def _prepare_targets(state, context):
    from dataclasses import asdict
    from .tasks import TaskPackCatalog, TASK_PACK_COMPONENT
    state = state.with_component(TASK_PACK_COMPONENT, TaskPackCatalog(context.workspace, context.task_pack_sources))
    editor = state.components[TEXT_TARGET_PREFIX + 'improvement-editor'].instructions
    evaluator = state.components[TEXT_TARGET_PREFIX + 'improvement-evaluator'].instructions
    settings = {'editor': {'model_role': 'editor', 'instructions': asdict(editor)},
        'evaluator': {'instructions': asdict(evaluator)}}
    organizer = state.components[TEXT_TARGET_PREFIX + 'improvement-organizer'].instructions
    settings['organizer'] = {'instructions': asdict(organizer)}
    for role, key in (('organizer', ORGANIZER_CONFIG), ('editor', EDITOR_CONFIG), ('assessor', ASSESSOR_CONFIG)):
        state = state.with_component(key, _lazy_role_config(state.config, context, role))
    return (state.with_component(SYSTEM_SETTINGS, settings)
        .with_component(EDITOR_INSTRUCTIONS, editor))


def _lazy_role_config(config, context, role):
    alias = context.model_roles.get(role)
    if alias is None or alias == context.model_roles.get('executor'):
        return replace(config, provider=RoleProvider(config.provider, 'component-improvement', role))
    if alias not in context.model_metadata:
        raise ValueError('unknown model role profile: ' + alias)
    metadata = context.model_metadata[alias]
    class LazyProvider:
        binding = None
        def __getattr__(self, name):
            if name not in {'input_count_supported', 'count_input', 'input_count_identity', 'can_rebase_context',
                    'context_usage_tokens', 'effective_output_limit', 'input_measurement_scope',
                    'input_estimation_messages', 'validate_input', 'vision'}:
                raise AttributeError(name)
            if self.binding is None:
                self.binding = context.provider_resolver(alias, None)
            return getattr(self.binding.provider, name)
        def __call__(self, view, *, signal=None):
            if self.binding is None:
                self.binding = context.provider_resolver(alias, None)
            return RoleProvider(self.binding.provider, 'component-improvement', role)(replace(view, model=self.binding.model), signal=signal)
        async def aclose(self):
            from inspect import isawaitable
            if self.binding is not None:
                close = getattr(self.binding.provider, 'aclose', None) or getattr(self.binding.provider, 'close', None)
                if close is not None:
                    result = close()
                    if isawaitable(result):
                        await result
    return replace(config, provider=context.own(LazyProvider()), **metadata)
