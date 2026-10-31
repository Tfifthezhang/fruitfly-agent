"""Fixed base prompt as a named text improvement target."""
from fruitfly_agent.improvement.contracts.optimization import OptimizationSpec
from dataclasses import replace
from fruitfly_agent.improvement.contracts.optimization import TargetBinding, TargetSnapshot
from fruitfly_agent.lab.improvement.targets.text import validate_text


class BasePromptTarget:
    description = 'Overall task-execution instructions: reasoning, tool use, and delivery. Does not change tools or permissions.'
    optimization = OptimizationSpec('H', 'text')
    optimization_field = 'instructions.system'
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
        if not isinstance(parameters,dict) or set(parameters)!={'instructions'} or not isinstance(parameters['instructions'],dict) or set(parameters['instructions'])!={'system'}:
            raise ValueError('base prompt requires instructions.system')
        validate_text(parameters['instructions']['system'])
        return parameters
    def reference(parameters):
        from . import builtins
        return next((p.prompt_id for p in builtins() if p.text==parameters['instructions']['system']),None)
    def options(fields,bounds):
        if fields!=['parameters.instructions.system'] or bounds:raise ValueError('base prompt grants require instructions.system')
        return {}
    return ConfigurationSurface('base_prompt','H','prompt','',normalize,
        encode=lambda p:p['instructions']['system'], decode=lambda text:{'instructions':{'system':text}},
        edit_options=options,reference=reference)
