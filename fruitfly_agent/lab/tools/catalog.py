"""One editable tool policy with source-owned, demand-loaded usage resources."""
from fruitfly_agent.runtime_spec.documents import parameter_default
from dataclasses import dataclass, replace
import json
import hashlib

from fruitfly_agent.core.context import ContextStage, ContextTransform
from fruitfly_agent.improvement.contracts.optimization import OptimizationSpec, TargetBinding, TargetSnapshot
from fruitfly_agent.lab.improvement.targets.text import TEXT_TARGET_PREFIX, validate_text
from .resources import ResourceRegistry


_START = '<!-- fruitfly:tool-catalog:start -->'
_END = '<!-- fruitfly:tool-catalog:end -->'


@dataclass(frozen=True)
class ToolCatalogProjection:
    block: str

    def transform(self, frame):
        prompt = frame.system_prompt
        while _START in prompt:
            start = prompt.index(_START)
            end = prompt.find(_END, start)
            if end < 0:
                raise ValueError('incomplete tool catalog projection')
            prompt = prompt[:start] + prompt[end + len(_END):]
        prompt = prompt.rstrip() + '\n\n' + self.block
        return None if prompt == frame.system_prompt else ContextTransform(replace(frame, system_prompt=prompt))


def configuration_surface():
    from fruitfly_agent.lab.catalog.configuration import ConfigurationSurface
    def normalize(value):
        if (not isinstance(value, dict) or set(value) != {'instructions'}
                or not isinstance(value['instructions'], dict) or set(value['instructions']) != {'usage'}):
            raise ValueError('tool catalog requires instructions.usage')
        ToolCatalogTarget().validate(value['instructions']['usage'])
        return value
    def options(fields, bounds):
        if fields != ['parameters.instructions.usage'] or bounds:
            raise ValueError('tool catalog grants permit instructions.usage only')
        return {}
    return ConfigurationSurface('tool-catalog', 'H', 'artifact', 'tool-catalog', normalize,
        encode=lambda value: value['instructions']['usage'],
        decode=lambda text: {'instructions': {'usage': text}}, edit_options=options,
        default=lambda: {'instructions': {'usage': parameter_default(__package__, 'tool-catalog.yaml', 'instructions.usage')}},
        default_resource=(__package__, 'tool-catalog.yaml'), standalone=True)


class ToolCatalogTarget:
    """Coordinate tool choice, composition, recovery and verification as one policy."""
    optimization = OptimizationSpec('H', 'text')
    component_kind = 'tool-catalog'
    label = 'Tool catalog policy'
    description = 'Overall tool selection, composition, failure recovery and verification policy. Tool identities, usage resources, schemas, permissions and implementations remain protected.'

    def __init__(self, usage=None):
        usage = parameter_default(__package__, 'tool-catalog.yaml', 'instructions.usage') if usage is None else usage
        self.validate(usage)
        self.usage = usage

    def snapshot(self):
        return TargetSnapshot('tool-catalog', self.usage, TargetBinding('artifact', 'tool-catalog'))

    def validate(self, text):
        validate_text(text)
        if len(text) > 12000 or _START in text or _END in text:
            raise ValueError('tool catalog policy must fit 12000 characters without projection markers')

    def prepare_trial(self, config, text):
        self.validate(text)
        tools = tuple(config.tools)
        visible = tuple(tool for tool in tools if not tool.hide_from_model)
        if not visible:
            return config
        resources = config.readable_resources or ResourceRegistry()
        documents = {tool.name + '.txt': tool.description.encode() for tool in visible}
        documents['index.json'] = json.dumps([{'name': tool.name, 'label': tool.label,
            'usage': tool.name + '.txt'} for tool in visible], ensure_ascii=False).encode()
        prefix = (f'resource://{resources.scope}/tools/' if 'tools' in resources.providers
                  else resources.mount('tools', lambda path: documents[path]))
        demand = any(tool.name == 'read' for tool in visible)
        rows = [text, '', 'Available tools (names and operation contracts are fixed):']
        rows.extend(f'- {tool.name}: {tool.label}. Full usage: {prefix}{tool.name}.txt'
                    if demand else f'- {tool.name}: {tool.label}' for tool in visible)
        if demand:
            tools = tuple(replace(tool, description=(
                tool.label + '. Read the full usage reference in the tool catalog before use.'
                + (' Accepts file paths and read-only resource:// references.' if tool.name == 'read' else '')))
                if not tool.hide_from_model else tool for tool in tools)
        prompt = config.system_prompt
        while _START in prompt:
            start = prompt.index(_START)
            end = prompt.find(_END, start)
            if end < 0:
                raise ValueError('incomplete tool catalog projection')
            prompt = prompt[:start] + prompt[end + len(_END):]
        prompt = prompt.rstrip() + '\n\n' + _START + '\n' + '\n'.join(rows) + '\n' + _END
        return replace(config, tools=tools, system_prompt=prompt, readable_resources=resources)


def prepare_catalog(state, context):
    contracts = tuple({'name': tool.name,
        'usage_sha256': 'sha256:' + hashlib.sha256(tool.description.encode()).hexdigest(),
        'schema_sha256': 'sha256:' + hashlib.sha256(json.dumps(tool.parameters,
            sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()}
        for tool in state.config.tools if not tool.hide_from_model)
    state = state.with_component('tool-contracts', contracts)
    reference = context.artifact_bindings.get('tool-catalog')
    text = context.artifact_reader(reference) if reference else parameter_default(__package__, 'tool-catalog.yaml', 'instructions.usage')
    target = ToolCatalogTarget(text)
    config = target.prepare_trial(state.config, text)
    if config.tools:
        start = config.system_prompt.find(_START)
        if start >= 0:
            state = state.with_context_stage(ContextStage('instruction-components.tool-catalog', 'augmentation',
                ToolCatalogProjection(config.system_prompt[start:]), order=20))
    config = replace(config, system_prompt=state.config.system_prompt)
    state = state.with_component(TEXT_TARGET_PREFIX + 'tool-catalog', target)
    if reference:
        state = state.with_data_artifact({'key': 'tool-catalog', 'id': reference,
            'media_type': 'text/plain; charset=utf-8', 'size_bytes': len(text.encode())})
    return replace(state, config=config)
