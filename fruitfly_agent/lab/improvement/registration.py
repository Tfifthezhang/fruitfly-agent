"""One generic workflow configuration; stage implementations are injected ports."""
from dataclasses import replace

from fruitfly_agent.core.mechanisms import MechanismDescriptor, MechanismContribution, MechanismEffects, ParameterDescriptor as P
from fruitfly_agent.lab.algorithms.targets import TEXT_TARGET_PREFIX
from .editor.instructions import EditorInstructions, EditorInstructionTarget


SETTINGS = 'component-improvement-settings'
EDITOR_CONFIG = 'component-improvement-editor-config'
ASSESSOR_CONFIG = 'component-improvement-assessor-config'
EDITOR_INSTRUCTIONS = 'component-improvement-editor-instructions'
SYSTEM_SETTINGS = 'system-component-settings'


def definition():
    from fruitfly_agent.lab.catalog.models import MechanismDefinition
    from fruitfly_agent.lab.catalog.components import ComponentSpec
    from .system_configuration import configuration_surfaces, validate_component_options
    return MechanismDefinition(MechanismDescriptor('component-improvement', 'Component improvement',
        'Configure shared editing and execution allocations without starting improvement.',
        contributions=(MechanismContribution('improvement', 'context'),),
        default_enabled=True,
        parameters=(P('editor_profile', 'string', 'Editor model', 'Model catalog profile; empty reuses the active model.', ''),
            P('assessor_profile', 'string', 'Assessment model', 'Model catalog profile; empty reuses the active model.', ''),
            P('max_model_calls', 'integer', 'Model calls', 'Root allocation across stages.', 64, minimum=1, maximum=10000),
            P('max_executions', 'integer', 'Task executions', 'Root execution allocation.', 32, minimum=1, maximum=1000),
            P('operation_timeout', 'number', 'Operation timeout', 'Seconds per stage.', 120, minimum=1, maximum=14400)),
        install_order=76, effects=MechanismEffects(uses_provider=True, uses_network=True, writes_files=True,
            cost_notice="Explicit improvement runs call models and execute tasks; registration makes no requests.")),
        _install, visible=False, implementation_id='component-workflow-v1', configuration_role='I',
        configuration_surfaces=configuration_surfaces(),
        model_role_parameters={'editor': 'editor_profile', 'assessor': 'assessor_profile'},
        component_validator=validate_component_options,
        model_profiles=lambda parameters: tuple(parameters[name] for name in ('editor_profile', 'assessor_profile') if parameters[name]),
        artifact_slots=frozenset({'improvement-editor', 'improvement-feedback', 'improvement-search'}), prepare_targets=_prepare_targets,
        component_specs=lambda parameters, enabled: (ComponentSpec('improvement-editor', 'I', kind='improvement-instructions', schema='editor-instructions-v3',
            required_capabilities=frozenset({'improver-comparison'})),),
        implementation_path='fruitfly_agent/lab/improvement/registration.py',
        documentation_path='fruitfly_agent/lab/improvement/README.md')


def _install(state, context, parameters):
    config = state.config
    if parameters['editor_profile']:
        binding = context.provider_resolver(parameters['editor_profile'], None)
        config = replace(config, provider=binding.provider, model=binding.model,
            context_window=binding.context_window or config.context_window,
            max_tokens=binding.max_output_tokens or config.max_tokens)
    assessor = state.config
    if parameters['assessor_profile']:
        binding = context.provider_resolver(parameters['assessor_profile'], None)
        assessor = replace(assessor, provider=binding.provider, model=binding.model,
            context_window=binding.context_window or assessor.context_window,
            max_tokens=binding.max_output_tokens or assessor.max_tokens)
    return (state.with_component(SETTINGS, dict(parameters)).with_component(EDITOR_CONFIG, config)
        .with_component(ASSESSOR_CONFIG, assessor))


def _prepare_targets(state, context):
    from .components.configuration import ImprovementSettingsTarget
    settings = dict(context.component_settings)
    for key in ('feedback', 'search'):
        name = 'improvement-' + key
        reference = context.artifact_bindings.get(name)
        if key in settings or reference is not None:
            target = ImprovementSettingsTarget(key, settings.get(key, {}))
            if reference is not None:
                text = context.artifact_reader(reference)
                target = ImprovementSettingsTarget(key, target.parse(text))
                state = state.with_data_artifact({'key': name, 'id': reference, 'role': 'I',
                    'media_type': 'application/json', 'size_bytes': len(text.encode('utf-8'))})
            settings[key] = target.parameters
            state = state.with_component(TEXT_TARGET_PREFIX + name, target)
    instructions = EditorInstructions(**context.component_settings.get('editor', {}).get('instructions', {}))
    turns = context.component_settings.get('editor', {}).get('max_turns', 12)
    calls = context.component_settings.get('editor', {}).get('max_tool_calls', 48)
    text = None
    reference = context.artifact_bindings.get('improvement-editor')
    if reference is not None:
        if context.artifact_reader is None:
            raise ValueError('editor instructions require an artifact reader')
        text = context.artifact_reader(reference)
        instructions, calls, turns = EditorInstructionTarget.parse_document(text)
        if 'editor' in settings:
            from dataclasses import asdict
            settings['editor'] = {**settings['editor'], 'instructions': asdict(instructions), 'max_tool_calls': calls, 'max_turns': turns}
        if not any(a['key'] == 'improvement-editor' for a in state.data_artifacts):
            state = state.with_data_artifact({'key': 'improvement-editor', 'id': reference, 'role': 'I',
                'media_type': 'application/json', 'size_bytes': len(text.encode('utf-8'))})
    for role, key in (('editor', EDITOR_CONFIG), ('assessor', ASSESSOR_CONFIG)):
        if key not in state.components:
            state = state.with_component(key, _lazy_role_config(state.config, context, role))
    return (state.with_component(SYSTEM_SETTINGS, settings)
        .with_component(EDITOR_INSTRUCTIONS, instructions)
        .with_component(TEXT_TARGET_PREFIX + 'improvement-editor', EditorInstructionTarget(instructions, max_tool_calls=calls, max_turns=turns, text=text)))


def _lazy_role_config(config, context, role):
    alias = context.model_roles.get(role)
    if alias is None or alias == context.model_roles.get('executor'):
        return config
    if alias not in context.model_metadata:
        raise ValueError('unknown model role profile: ' + alias)
    metadata = context.model_metadata[alias]
    class LazyProvider:
        binding = None
        def __getattr__(self, name):
            if name not in {'input_count_supported', 'count_input', 'input_count_identity', 'can_rebase_context',
                    'context_usage_tokens', 'effective_output_limit', 'input_measurement_scope'}:
                raise AttributeError(name)
            if self.binding is None:
                self.binding = context.provider_resolver(alias, None)
            return getattr(self.binding.provider, name)
        def __call__(self, view, *, signal=None):
            if self.binding is None:
                self.binding = context.provider_resolver(alias, None)
            return self.binding.provider(replace(view, model=self.binding.model), signal=signal)
        async def aclose(self):
            from inspect import isawaitable
            if self.binding is not None:
                close = getattr(self.binding.provider, 'aclose', None) or getattr(self.binding.provider, 'close', None)
                if close is not None:
                    result = close()
                    if isawaitable(result):
                        await result
    return replace(config, provider=context.own(LazyProvider()), **metadata)
