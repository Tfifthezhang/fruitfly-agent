"""Generic durable checkpoints and paged collaboration, supplied by a host."""
import json
from dataclasses import replace
from fruitfly_agent.core.tool_runtime import AgentTool
from fruitfly_agent.core.data_model import AgentToolResult, TextBlock


def work_product_tools(store, parameters):
    def result(value):
        return AgentToolResult([TextBlock(json.dumps(value, ensure_ascii=False))])
    async def save(ctx):
        row = store.save(ctx.args['name'], ctx.args['content'], ctx.args['expected_revision'])
        return result({**row, 'scope': 'Working material; not a verified result or an original-reading receipt.'})
    async def catalog(ctx):
        offset, limit = ctx.args.get('offset', 0), ctx.args.get('limit', parameters['directory_entries'])
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('invalid work product directory page')
        rows = [{k: v for k, v in row.items() if k != 'previous'} for row in store.entries()]
        end = offset + limit
        return result({'products': rows[offset:end], 'next_offset': end if end < len(rows) else None})
    async def read(ctx):
        text = store.read(ctx.args['producer'], ctx.args['name'], ctx.args['revision'])
        offset, limit = ctx.args.get('offset', 0), ctx.args.get('limit', parameters['page_characters'])
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 24000:
            raise ValueError('invalid work product character page')
        end = min(len(text), offset + limit)
        return result({'text': text[offset:end], 'next_offset': end if end < len(text) else None,
                       'scope': 'Derived working material; verify facts through their original sources.'})
    async def patch(ctx):
        current = store.read(store.producer, ctx.args['name'], ctx.args['expected_revision'])
        from fruitfly_agent.lab.agents.submissions import load_submission
        value = load_submission(current)
        for change in ctx.args['changes']:
            path = change['path']
            if not isinstance(path, list) or not path or len(path) > 64:
                raise ValueError('patch path must name an existing JSON field')
            parent = value
            for part in path[:-1]:
                parent = parent[int(part)] if isinstance(parent, list) else parent[part]
            key = int(path[-1]) if isinstance(parent, list) else path[-1]
            if change['operation'] == 'remove':
                del parent[key]
            else:
                parent[key] = json.loads(change['value'])
        return result(store.save(ctx.args['name'], json.dumps(value, ensure_ascii=False), ctx.args['expected_revision']))
    text = {'type': 'string'}
    integer = {'type': 'integer', 'minimum': 0}
    def tool(name, description, properties, required, execute):
        return AgentTool(name=name, label=name.replace('_', ' '), description=description,
            parameters={'type': 'object', 'properties': properties, 'required': required,
                        'additionalProperties': False}, execute=execute)
    return (
        tool('patch_checkpoint', parameters['patch'],
             {'name': text, 'expected_revision': integer, 'changes': {'type': 'array', 'items': {
                 'type': 'object', 'properties': {'path': {'type': 'array', 'items': text},
                     'operation': {'type': 'string', 'enum': ['replace', 'remove']}, 'value': text},
                 'required': ['path', 'operation'], 'additionalProperties': False}}},
             ['name', 'expected_revision', 'changes'], patch),
        tool('save_checkpoint', parameters['checkpoint'],
             {'name': text, 'content': text, 'expected_revision': integer}, ['name', 'content', 'expected_revision'], save),
        tool('list_work_products', parameters['catalog'],
             {'offset': integer, 'limit': integer}, [], catalog),
        tool('read_work_product', parameters['read'],
             {'producer': text, 'name': text, 'revision': integer, 'offset': integer, 'limit': integer},
             ['producer', 'name', 'revision'], read))


def install_work_products(state, context, parameters):
    if context.work_products is None:
        raise ValueError("work-products requires an explicit durable host store")
    tools = work_product_tools(context.work_products, parameters)
    names = {t.name for t in state.config.tools}
    if names & {t.name for t in tools}:
        raise ValueError('work product tool name collision')
    from fruitfly_agent.core.extensions.hooks import HookRegistry, BEFORE_REQUEST
    hooks = state.config.hooks.clone() if state.config.hooks else HookRegistry(session=context.session)
    notified = False
    async def visibility(event):
        nonlocal notified
        available = context.work_products.has_products()
        event.tools = tuple(replace(t, hide_from_model=not available) if t.name in
            {'list_work_products', 'read_work_product', 'patch_checkpoint'} else t for t in event.tools)
        meter = state.config.context_meter
        if meter is not None:
            from fruitfly_agent.core.data_model import ProviderView, CustomMessage
            measured = await meter.measure(ProviderView(event.system_prompt, list(event.messages),
                list(event.tools), event.model, event.max_tokens), state.config.provider)
            capacity = max(1, state.config.context_window - measured.output_reserve - measured.margin)
            pressure = measured.input_tokens is not None and measured.input_tokens >= capacity * parameters['pressure_ratio']
            if pressure and not notified:
                event.messages = [*event.messages, CustomMessage('work-product-pressure',
                    parameters['checkpoint'] + ' Retain unfinished scope and focus on integration and delivery; avoid expanding the investigation unnecessarily.')]
                if context.session is not None:
                    context.session.append('meta', {'kind': 'work-product-pressure', 'input_tokens': measured.input_tokens})
            notified = pressure
        return event
    hooks.add(BEFORE_REQUEST, visibility)
    return replace(state, config=replace(state.config, tools=(*state.config.tools, *tools), hooks=hooks))
