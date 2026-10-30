"""Fixed base prompt as a named text improvement target."""
from fruitfly_agent.improvement.contracts.optimization import OptimizationSpec
from dataclasses import replace
from fruitfly_agent.improvement.contracts.optimization import TargetBinding, TargetSnapshot
from fruitfly_agent.lab.improvement.targets.text import validate_text


class BasePromptTarget:
    optimization = OptimizationSpec('H', 'text')
    label = 'Base prompt'
    component_kind = 'system-prompt'

    def __init__(self, text):
        self.text = text

    def snapshot(self):
        return TargetSnapshot('base_prompt', self.text, TargetBinding('prompt'))

    def validate(self, text):
        validate_text(text)

    def prepare_trial(self, config, text):
        self.validate(text)
        return replace(config, system_prompt=text)


def configuration_surface():
    from fruitfly_agent.lab.catalog.configuration import ConfigurationSurface, text_edit_options
    def normalize(parameters):
        if set(parameters) != {'text'}:
            raise ValueError('base_prompt parameters require text')
        validate_text(parameters['text'])
        return parameters
    def reference(parameters):
        from . import builtins
        return next((prompt.prompt_id for prompt in builtins() if prompt.text == parameters['text']), None)
    return ConfigurationSurface('base_prompt', 'H', 'prompt', '', normalize,
                                edit_options=text_edit_options, reference=reference)
