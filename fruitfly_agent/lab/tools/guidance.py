"""Tool-owned instruction bindings; implementations and schemas stay unchanged."""
from fruitfly_agent.improvement.contracts.optimization import OptimizationSpec
from dataclasses import replace

from fruitfly_agent.improvement.contracts.optimization import TargetBinding, TargetSnapshot
from fruitfly_agent.lab.improvement.targets.text import validate_text


def guidance_key(name):
    return 'tool-guidance.' + name


def configuration_surface(name, *, tool_factory=None):
    from fruitfly_agent.lab.catalog.configuration import ConfigurationSurface, text_edit_options
    def normalize(parameters):
        if set(parameters) != {'text'}:
            raise ValueError('tool guidance parameters require text')
        validate_text(parameters['text'])
        if len(parameters['text']) > 6000:
            raise ValueError('tool guidance exceeds 6000 characters')
        return parameters
    return ConfigurationSurface(guidance_key(name), 'H', 'artifact', guidance_key(name), normalize,
        edit_options=text_edit_options,
        default=(lambda: {'text': tool_factory().description}) if tool_factory is not None else None)


class ToolGuidanceTarget:
    requires_runtime_trials = True
    component_kind = 'tool-guidance'

    def __init__(self, tool):
        self.tool = tool
        self.label = tool.label + ' guidance'
        self.required_capabilities = frozenset({'tool:' + tool.name})
        self.optimization = OptimizationSpec('H', 'text', required_capabilities=self.required_capabilities)

    def snapshot(self):
        key = guidance_key(self.tool.name)
        return TargetSnapshot(key, self.tool.description, TargetBinding('artifact', key))

    def validate(self, text):
        validate_text(text)
        if len(text) > 6000:
            raise ValueError('tool guidance exceeds 6000 characters')

    def prepare_trial(self, config, text):
        self.validate(text)
        if self.tool.name not in {t.name for t in config.tools}:
            raise ValueError('tool guidance requires the selected tool in an isolated runtime')
        return replace(config, tools=tuple(replace(t, description=text) if t.name == self.tool.name else t
                                           for t in config.tools))


def prepare_guidance(state, context):
    """Consume enabled tools' declared artifacts and expose their exact instructions."""
    from fruitfly_agent.lab.improvement.targets.text import TEXT_TARGET_PREFIX
    config = state.config
    for tool in tuple(config.tools):
        target = ToolGuidanceTarget(tool)
        key = target.snapshot().binding.key
        reference = context.artifact_bindings.get(key)
        if reference is not None:
            if context.artifact_reader is None:
                raise ValueError('tool guidance requires an artifact reader')
            text = context.artifact_reader(reference)
            config = target.prepare_trial(config, text)
            target = ToolGuidanceTarget(next(t for t in config.tools if t.name == tool.name))
            if not any(a.get('key') == key for a in state.data_artifacts):
                state = state.with_data_artifact({'key': key, 'id': reference,
                    'media_type': 'text/plain; charset=utf-8', 'size_bytes': len(text.encode('utf-8'))})
        state = state.with_component(TEXT_TARGET_PREFIX + key, target)
    return replace(state, config=config)
