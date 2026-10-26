"""Fixed base prompt as a named text improvement target."""
from dataclasses import replace
from fruitfly_agent.lab.algorithms.targets import TargetBinding, TargetSnapshot, validate_text


class BasePromptTarget:
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
