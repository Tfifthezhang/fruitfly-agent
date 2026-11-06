"""Project a bounded memory directory independently of information ranking."""
from dataclasses import dataclass, replace
from fruitfly_agent.core.context import ContextStage, ContextTransform
from fruitfly_agent.lab.catalog.assembly import require_workspace_path
from fruitfly_agent.improvement.contracts.text import TEXT_TARGET_PREFIX
from .resources import mount_memories
from .index import render_catalog

_START = '<!-- fruitfly:memory:start -->'
_END = '<!-- fruitfly:memory:end -->'


@dataclass(frozen=True)
class MemoryDirectory:
    text: str

    def transform(self, frame):
        prompt = frame.system_prompt
        while _START in prompt:
            start = prompt.index(_START)
            end = prompt.find(_END, start)
            if end < 0:
                raise ValueError('incomplete memory directory projection')
            prompt = prompt[:start] + prompt[end + len(_END):]
        prompt = prompt.rstrip() + '\n\n' + _START + '\n' + self.text + '\n' + _END
        return None if prompt == frame.system_prompt else ContextTransform(replace(frame, system_prompt=prompt))


def install_reading(state, context, values):
    require_workspace_path(context.workspace, values['root'], name='memory namespace')
    target = state.components[TEXT_TARGET_PREFIX + 'memory-library']
    entries = target.list_entries()
    locations = mount_memories(context.resources, entries)
    directory = render_catalog(entries, locations, max_chars=values['max_chars'])
    return state.with_context_stage(ContextStage('file-memory', 'augmentation',
        MemoryDirectory(values['usage'] + '\n\n' + directory), order=40))
