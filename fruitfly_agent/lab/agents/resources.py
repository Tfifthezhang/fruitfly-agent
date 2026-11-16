"""Bind scoped runtime resources to a host's existing read tool."""
from dataclasses import replace
import json
from fruitfly_agent.core.data_model import AgentToolResult, TextBlock
from fruitfly_agent.lab.tools.resources import is_resource


def bind_resource_reader(tools, resources, *, page_characters):
    result = []
    for tool in tools:
        if tool.name != 'read':
            result.append(tool)
            continue
        async def read(ctx, original=tool.execute):
            path = ctx.args['path']
            if not is_resource(path):
                return await original(ctx)
            offset, limit = ctx.args.get('offset', 0), ctx.args.get('limit', page_characters)
            if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= page_characters:
                raise ValueError('invalid resource character page')
            text = resources.read(path.lstrip('@')).decode('utf-8')
            end = min(len(text), offset + limit)
            return AgentToolResult([TextBlock(json.dumps({'path': path, 'text': text[offset:end],
                'next_offset': end if end < len(text) else None,
                'scope': 'Derived runtime material; no new original-evidence citation.'}, ensure_ascii=False))])
        result.append(replace(tool, execute=read, description=tool.description +
            ' Read resource:// references with character offset/limit to recover archived history or work products.'))
    return tuple(result)
