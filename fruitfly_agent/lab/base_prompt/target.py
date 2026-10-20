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
