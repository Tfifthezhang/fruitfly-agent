"""One generic workflow configuration; stage implementations are injected ports."""
from dataclasses import replace

from fruitfly_agent.core.mechanisms import MechanismDescriptor, MechanismContribution, MechanismEffects, ParameterDescriptor as P
from fruitfly_agent.lab.algorithms.targets import TEXT_TARGET_PREFIX
from .editor.instructions import EditorInstructions, EditorInstructionTarget


SETTINGS = 'component-improvement-settings'
EDITOR_CONFIG = 'component-improvement-editor-config'
EDITOR_INSTRUCTIONS = 'component-improvement-editor-instructions'


def definition():
    from fruitfly_agent.lab.catalog.models import MechanismDefinition
    return MechanismDefinition(MechanismDescriptor('component-improvement', 'Component improvement',
        'Configure shared editing and execution allocations without starting improvement.',
        contributions=(MechanismContribution('improvement', 'context'),),
        default_enabled=True,
        parameters=(P('editor_profile', 'string', 'Editor model', 'Model catalog profile; empty reuses the active model.', ''),
            P('max_model_calls', 'integer', 'Model calls', 'Root allocation across stages.', 64, minimum=1, maximum=10000),
            P('max_executions', 'integer', 'Task executions', 'Root execution allocation.', 32, minimum=1, maximum=1000),
            P('operation_timeout', 'number', 'Operation timeout', 'Seconds per stage.', 120, minimum=1, maximum=14400)),
        install_order=76, effects=MechanismEffects(uses_provider=True, uses_network=True, writes_files=True,
            cost_notice="Explicit improvement runs call models and execute tasks; registration makes no requests.")),
        _install, visible=False, implementation_id='component-workflow-v1',
        artifact_slots=frozenset({'improvement-editor'}), prepare_targets=_prepare_targets,
        implementation_path='fruitfly_agent/lab/improvement/registration.py',
        documentation_path='fruitfly_agent/lab/improvement/README.md')


def _install(state, context, parameters):
    config = state.config
    if parameters['editor_profile']:
        binding = context.provider_resolver(parameters['editor_profile'], None)
        config = replace(config, provider=binding.provider, model=binding.model,
            context_window=binding.context_window or config.context_window,
            max_tokens=binding.max_output_tokens or config.max_tokens)
    return state.with_component(SETTINGS, dict(parameters)).with_component(EDITOR_CONFIG, config)


def _prepare_targets(state, context):
    instructions = EditorInstructions()
    reference = context.artifact_bindings.get('improvement-editor')
    if reference is not None:
        if context.artifact_reader is None:
            raise ValueError('editor instructions require an artifact reader')
        text = context.artifact_reader(reference)
        instructions = EditorInstructions.parse(text)
        if not any(a['key'] == 'improvement-editor' for a in state.data_artifacts):
            state = state.with_data_artifact({'key': 'improvement-editor', 'id': reference, 'role': 'I',
                'media_type': 'application/json', 'size_bytes': len(text.encode('utf-8'))})
    return (state.with_component(EDITOR_INSTRUCTIONS, instructions)
        .with_component(TEXT_TARGET_PREFIX + 'improvement-editor', EditorInstructionTarget(instructions)))
