"""Loadable, optimizable instruction extension. Registration is offline."""
from fruitfly_agent.improvement.contracts.optimization import OptimizationSpec
from dataclasses import replace

from fruitfly_agent.lab.catalog import MechanismDefinition, MechanismDescriptor, MechanismContribution
from fruitfly_agent.lab.catalog.components import ComponentSpec
from fruitfly_agent.lab.catalog.configuration import ConfigurationSurface, text_edit_options
from fruitfly_agent.improvement.contracts.optimization import TargetSnapshot, TargetBinding
from fruitfly_agent.lab.improvement.targets.text import TEXT_TARGET_PREFIX, validate_text

TARGET = 'developer-guidance'
DEFAULT = 'Use concrete evidence and state the next useful action.'
MARKER = '\n\n<developer-guidance>\n'


def normalize(parameters):
    if not isinstance(parameters, dict) or set(parameters) - {'text'}:
        raise ValueError('guidance permits only text')
    text = parameters.get('text', DEFAULT)
    validate_text(text)
    return {'text': text}


class GuidanceTarget:
    optimization = OptimizationSpec('H', 'text')
    def __init__(self, text):
        self.text = text

    def snapshot(self):
        return TargetSnapshot(TARGET, self.text, TargetBinding('artifact', TARGET))

    def validate(self, text):
        validate_text(text)

    def prepare_trial(self, config, text):
        self.validate(text)
        prefix = config.system_prompt.split(MARKER, 1)[0]
        return replace(config, system_prompt=prefix + MARKER + text + '\n</developer-guidance>')


def install(state, context, parameters):
    reference = context.artifact_bindings.get(TARGET)
    text = context.artifact_reader(reference) if reference is not None else DEFAULT
    target = GuidanceTarget(text)
    if reference is not None:
        state = state.with_data_artifact({'key': TARGET, 'id': reference,
            'media_type': 'text/plain; charset=utf-8', 'size_bytes': len(text.encode())})
    return replace(state, config=target.prepare_trial(state.config, text)).with_component(TEXT_TARGET_PREFIX + TARGET, target)


def register(api):
    api.register_mechanism(MechanismDefinition(
        MechanismDescriptor('developer-guidance-owner', 'Developer guidance',
            'Apply independently editable task guidance to model requests.',
            contributions=(MechanismContribution('capability', 'context'),)), install,
        implementation_id='developer-guidance-v1',
        implementation_path='examples/extensions/developer_guidance.py',
        documentation_path='examples/extensions/README.md', artifact_slots=frozenset({TARGET}),
        component_specs=lambda parameters, enabled: (ComponentSpec(TARGET),) if enabled else (),
        configuration_surfaces=(ConfigurationSurface(TARGET, 'H', 'artifact', TARGET, normalize,
            edit_options=text_edit_options),)))
